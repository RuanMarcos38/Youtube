from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from openai import OpenAI

from ..config import settings
from . import editor_ai
from .editor_ai_pro import DEFAULT_EDIT_OPTIONS
from .ffmpeg_service import ensure_ffmpeg, get_duration


logger = logging.getLogger(__name__)

AI_VIDEO_QUEUED = "ai_video_queued"
AI_VIDEO_SUBMITTED = "ai_video_submitted"
AI_VIDEO_PROCESSING = "ai_video_processing"
AI_VIDEO_DOWNLOADING = "ai_video_downloading"
AI_VIDEO_WORKING_STATUSES = {
    AI_VIDEO_QUEUED,
    AI_VIDEO_SUBMITTED,
    AI_VIDEO_PROCESSING,
    AI_VIDEO_DOWNLOADING,
}
AI_VIDEO_DONE_STATUSES = {"uploaded", "ready", "exported", "failed", "cancelled"}

ASPECT_RATIOS = {"9:16", "16:9"}
RESOLUTIONS = {"720p", "1080p"}
MODES = {"fast", "quality"}
STYLES = {"cinematic", "creative", "ugc", "product"}
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_MAX_REQUESTS = 3
_RATE_LIMIT: dict[int, list[float]] = {}


@dataclass(frozen=True)
class AiVideoRequest:
    prompt: str
    model: str
    aspect_ratio: Literal["9:16", "16:9"]
    resolution: Literal["720p", "1080p"]
    duration_seconds: int
    style: str


class AiVideoProviderError(RuntimeError):
    def __init__(self, message: str, *, code: str = "provider_error"):
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str, fallback: str = "video") -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return (normalized or fallback)[:48]


def _model_for_mode(mode: str) -> str:
    if mode == "fast":
        return settings.veo_fast_model.strip()
    return settings.veo_quality_model.strip()


def _friendly_provider_error(payload: dict[str, Any], fallback: str) -> AiVideoProviderError:
    error = payload.get("error") if isinstance(payload, dict) else None
    code = str((error or {}).get("code") or (error or {}).get("status") or "provider_error")
    message = str((error or {}).get("message") or fallback).strip()
    lowered = message.lower()
    if any(term in lowered for term in ("quota", "rate", "resource exhausted")):
        return AiVideoProviderError("Limite do provedor de IA atingido. Tente novamente mais tarde.", code=code)
    if any(term in lowered for term in ("permission", "api key", "unauthenticated", "forbidden")):
        return AiVideoProviderError("A configuração do provedor de vídeo IA precisa ser revisada pelo administrador.", code=code)
    if any(term in lowered for term in ("safety", "policy", "blocked")):
        return AiVideoProviderError("Não foi possível gerar este vídeo porque a solicitação não foi aceita pelo provedor de IA.", code=code)
    return AiVideoProviderError("Não foi possível concluir a geração. Tente novamente.", code=code)


def ai_video_options() -> dict[str, Any]:
    configured = bool(settings.gemini_api_key.strip())
    enabled = bool(settings.ai_video_enabled)
    reason = ""
    if not enabled:
        reason = "Geração de vídeo IA está desativada."
    elif not configured:
        reason = "Configure GEMINI_API_KEY no serviço ShortsFlow AI para habilitar Veo."
    return {
        "enabled": enabled,
        "configured": configured,
        "available": enabled and configured,
        "unavailable_reason": reason,
        "prompt_improvement_available": bool(settings.openai_api_key.strip()),
        "audio_supported": True,
        "defaults": {
            "aspect_ratio": "9:16",
            "resolution": "1080p",
            "duration_seconds": 8,
            "mode": "fast",
            "style": "cinematic",
        },
        "aspect_ratios": [
            {"id": "9:16", "label": "9:16 - Shorts / TikTok"},
            {"id": "16:9", "label": "16:9 - Horizontal"},
        ],
        "resolutions": [
            {"id": "720p", "label": "720p"},
            {"id": "1080p", "label": "1080p"},
        ],
        "modes": [
            {"id": "fast", "label": "Rápido", "configured": bool(settings.veo_fast_model.strip())},
            {"id": "quality", "label": "Alta qualidade", "configured": bool(settings.veo_quality_model.strip())},
        ],
        "styles": [
            {"id": "cinematic", "label": "Cinematográfico"},
            {"id": "creative", "label": "Social criativo"},
            {"id": "ugc", "label": "UGC natural"},
            {"id": "product", "label": "Produto / vendas"},
        ],
        "durations": [{"id": 8, "label": "8 segundos"}],
    }


def ensure_ai_video_available() -> None:
    options = ai_video_options()
    if not options["available"]:
        raise RuntimeError(options["unavailable_reason"])


def enforce_ai_video_rate_limit(user_id: int) -> None:
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    recent = [item for item in _RATE_LIMIT.get(user_id, []) if item >= window_start]
    if len(recent) >= RATE_LIMIT_MAX_REQUESTS:
        raise RuntimeError("Aguarde um pouco antes de solicitar outra geração de vídeo IA.")
    recent.append(now)
    _RATE_LIMIT[user_id] = recent


def improve_prompt(prompt: str) -> str:
    if not settings.openai_api_key.strip():
        raise RuntimeError("Melhoria de prompt indisponível porque OPENAI_API_KEY não está configurada.")
    source = re.sub(r"\s+", " ", prompt).strip()
    client = OpenAI(api_key=settings.openai_api_key)
    response = client.responses.create(
        model=settings.openai_text_model,
        input=[
            {
                "role": "system",
                "content": (
                    "Você melhora prompts para geração de vídeo no ShortsFlow AI. "
                    "Preserve a intenção do usuário, não invente marcas, pessoas reais ou promessas, "
                    "e retorne apenas o prompt final em português claro."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Reescreva este prompt para Veo com descrição visual, câmera, iluminação, ritmo, "
                    "formato vertical quando fizer sentido e áudio ambiente, mantendo a intenção original:\n\n"
                    f"{source}"
                ),
            },
        ],
    )
    improved = str(getattr(response, "output_text", "") or "").strip()
    return improved or source


def _existing_project_for_request(user_id: int, request_id: str | None) -> dict[str, Any] | None:
    if not request_id:
        return None
    for project in editor_ai.list_projects(user_id):
        generation = project.get("ai_video_generation") or {}
        if generation.get("request_id") == request_id:
            return project
    return None


def _build_provider_prompt(prompt: str, *, aspect_ratio: str, resolution: str, style: str) -> str:
    style_label = {
        "cinematic": "visual cinematografico, camera suave, iluminacao profissional",
        "creative": "visual social criativo, ritmo dinamico, cortes naturais para shorts",
        "ugc": "aparencia UGC natural, realista, espontanea, camera de celular premium",
        "product": "video de produto e vendas, foco claro no beneficio visual, acabamento premium",
    }.get(style, "visual cinematografico")
    format_hint = "vertical para YouTube Shorts e TikTok" if aspect_ratio == "9:16" else "horizontal 16:9"
    return (
        f"{prompt.strip()}\n\n"
        f"Formato: {format_hint}. Resolucao solicitada: {resolution}. "
        f"Estilo: {style_label}. Gere movimento de camera coerente, boa iluminacao, "
        "composicao limpa e audio nativo quando apropriado. Nao inclua textos ilegíveis na imagem."
    )


def queue_ai_video_project(
    *,
    user_id: int,
    tenant_id: int,
    prompt: str,
    aspect_ratio: str = "9:16",
    resolution: str = "1080p",
    mode: str = "fast",
    style: str = "cinematic",
    request_id: str | None = None,
) -> dict[str, Any]:
    ensure_ai_video_available()
    aspect_ratio = aspect_ratio if aspect_ratio in ASPECT_RATIOS else "9:16"
    resolution = resolution if resolution in RESOLUTIONS else "1080p"
    mode = mode if mode in MODES else "fast"
    style = style if style in STYLES else "cinematic"
    model = _model_for_mode(mode)
    if not model:
        raise RuntimeError("Modelo Veo não configurado para o modo selecionado.")

    existing = _existing_project_for_request(user_id, request_id)
    if existing:
        return existing

    created_at = _now()
    title = _slug(prompt, "video-ia")
    project = editor_ai.create_project_record(
        user_id=user_id,
        tenant_id=tenant_id,
        original_filename=f"{title}-veo.mp4",
        stored_filename="source.mp4",
        preset="fast_retention",
        target_platform="youtube_shorts" if aspect_ratio == "9:16" else "horizontal",
        created_at=created_at,
    )
    project["status"] = AI_VIDEO_QUEUED
    project["progress"] = 1
    project["edit_options"] = dict(DEFAULT_EDIT_OPTIONS)
    project["ai_video_generation"] = {
        "request_id": request_id,
        "provider": "google_veo",
        "status": "queued",
        "prompt": prompt.strip(),
        "provider_prompt": _build_provider_prompt(prompt, aspect_ratio=aspect_ratio, resolution=resolution, style=style),
        "model_mode": mode,
        "model": model,
        "aspect_ratio": aspect_ratio,
        "resolution": resolution,
        "duration_seconds": 8,
        "style": style,
        "audio_requested": True,
        "provider_operation_id": None,
        "error_code": None,
        "error_message": None,
        "created_at": created_at,
        "submitted_at": None,
        "completed_at": None,
    }
    return editor_ai.save_project(user_id, project["id"], project)


class GoogleVeoProvider:
    base_url = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        if not self.api_key:
            raise AiVideoProviderError("A configuração do provedor de vídeo IA precisa ser revisada pelo administrador.", code="missing_api_key")

    @property
    def _headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}

    def submit(self, request: AiVideoRequest) -> str:
        payload = {
            "instances": [{"prompt": request.prompt}],
            "parameters": {
                "aspectRatio": request.aspect_ratio,
                "durationSeconds": str(request.duration_seconds),
                "resolution": request.resolution,
                "personGeneration": "allow_all",
            },
        }
        url = f"{self.base_url}/models/{request.model}:predictLongRunning"
        try:
            response = httpx.post(
                url,
                headers=self._headers,
                json=payload,
                timeout=settings.ai_video_request_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise AiVideoProviderError("Não foi possível conectar ao provedor de vídeo IA.", code="network_error") from exc
        data = self._json_or_error(response, "Falha ao solicitar geração de vídeo IA.")
        name = str(data.get("name") or "").strip()
        if not name:
            raise AiVideoProviderError("O provedor de vídeo IA não retornou o identificador da operação.", code="missing_operation")
        return name

    def operation(self, operation_name: str) -> dict[str, Any]:
        safe_name = operation_name.strip().lstrip("/")
        try:
            response = httpx.get(
                f"{self.base_url}/{safe_name}",
                headers={"x-goog-api-key": self.api_key},
                timeout=settings.ai_video_request_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise AiVideoProviderError("Não foi possível consultar o status da geração.", code="network_error") from exc
        return self._json_or_error(response, "Falha ao consultar geração de vídeo IA.")

    def download(self, video_uri: str, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".tmp")
        try:
            with httpx.stream(
                "GET",
                video_uri,
                headers={"x-goog-api-key": self.api_key},
                follow_redirects=True,
                timeout=max(60.0, settings.ai_video_request_timeout_seconds),
            ) as response:
                if response.status_code >= 400:
                    raw = response.read()
                    try:
                        payload = json.loads(raw.decode("utf-8"))
                    except Exception:
                        payload = {"error": {"message": "Falha ao baixar vídeo gerado.", "code": response.status_code}}
                    raise _friendly_provider_error(payload, "Falha ao baixar vídeo gerado.")
                with temp.open("wb") as handle:
                    for chunk in response.iter_bytes():
                        if chunk:
                            handle.write(chunk)
        except httpx.HTTPError as exc:
            temp.unlink(missing_ok=True)
            raise AiVideoProviderError("Não foi possível baixar o vídeo gerado.", code="download_error") from exc
        temp.replace(target)

    @staticmethod
    def _json_or_error(response: httpx.Response, fallback: str) -> dict[str, Any]:
        if response.status_code < 400:
            return response.json()
        try:
            payload = response.json()
        except Exception:
            payload = {"error": {"message": fallback, "code": response.status_code}}
        raise _friendly_provider_error(payload, fallback)


def _operation_error(operation: dict[str, Any]) -> AiVideoProviderError | None:
    error = operation.get("error")
    if not error:
        return None
    return _friendly_provider_error({"error": error}, "Geração de vídeo falhou.")


def _operation_video_uri(operation: dict[str, Any]) -> str:
    response = operation.get("response") or {}
    generated = (response.get("generateVideoResponse") or {}).get("generatedSamples") or []
    if generated:
        video = (generated[0] or {}).get("video") or {}
        uri = str(video.get("uri") or "").strip()
        if uri:
            return uri
    generated_videos = response.get("generatedVideos") or response.get("generated_videos") or []
    if generated_videos:
        video = (generated_videos[0] or {}).get("video") or {}
        uri = str(video.get("uri") or video.get("url") or "").strip()
        if uri:
            return uri
    return ""


def _update_generation(project: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    generation = dict(project.get("ai_video_generation") or {})
    generation.update(patch)
    project["ai_video_generation"] = generation
    return project


def _set_ai_video_state(
    user_id: int,
    project_id: str,
    *,
    status: str,
    progress: int,
    generation_patch: dict[str, Any] | None = None,
    error: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    project = editor_ai.read_project(user_id, project_id)
    if generation_patch:
        _update_generation(project, generation_patch)
    project["status"] = status
    project["progress"] = max(0, min(100, int(progress)))
    project["error"] = error
    project.update(extra)
    return editor_ai.save_project(user_id, project_id, project)


def _validate_generated_video(target: Path) -> float:
    if not target.is_file() or target.stat().st_size <= 0:
        raise AiVideoProviderError("O vídeo gerado não pôde ser validado.", code="invalid_file")
    ensure_ffmpeg()
    duration = get_duration(target)
    if duration <= 0:
        raise AiVideoProviderError("O vídeo gerado não possui duração válida.", code="invalid_duration")
    return duration


def run_ai_video_generation(user_id: int, project_id: str) -> None:
    provider = GoogleVeoProvider(settings.gemini_api_key)
    project = editor_ai.read_project(user_id, project_id)
    generation = dict(project.get("ai_video_generation") or {})
    root = editor_ai.project_dir(user_id, project_id)
    target = root / str(project.get("source_filename") or "source.mp4")
    operation_name = str(generation.get("provider_operation_id") or "").strip()

    try:
        if not operation_name:
            request = AiVideoRequest(
                prompt=str(generation.get("provider_prompt") or generation.get("prompt") or ""),
                model=str(generation.get("model") or settings.veo_fast_model),
                aspect_ratio=generation.get("aspect_ratio") if generation.get("aspect_ratio") in ASPECT_RATIOS else "9:16",
                resolution=generation.get("resolution") if generation.get("resolution") in RESOLUTIONS else "1080p",
                duration_seconds=8,
                style=str(generation.get("style") or "cinematic"),
            )
            operation_name = provider.submit(request)
            _set_ai_video_state(
                user_id,
                project_id,
                status=AI_VIDEO_SUBMITTED,
                progress=8,
                generation_patch={
                    "status": "submitted",
                    "provider_operation_id": operation_name,
                    "submitted_at": _now(),
                },
            )

        operation: dict[str, Any] = {}
        attempts = max(1, int(settings.ai_video_max_poll_attempts))
        for attempt in range(attempts):
            operation = provider.operation(operation_name)
            if operation.get("done"):
                break
            progress = min(88, 12 + int((attempt / max(1, attempts - 1)) * 70))
            _set_ai_video_state(
                user_id,
                project_id,
                status=AI_VIDEO_PROCESSING,
                progress=progress,
                generation_patch={"status": "processing"},
            )
            time.sleep(max(5.0, float(settings.ai_video_poll_seconds)))
        else:
            raise AiVideoProviderError("A geração demorou mais que o esperado. Tente consultar novamente em instantes.", code="timeout")

        provider_error = _operation_error(operation)
        if provider_error:
            raise provider_error
        video_uri = _operation_video_uri(operation)
        if not video_uri:
            raise AiVideoProviderError("O provedor concluiu a geração sem retornar o vídeo.", code="missing_video")

        _set_ai_video_state(
            user_id,
            project_id,
            status=AI_VIDEO_DOWNLOADING,
            progress=92,
            generation_patch={"status": "downloading"},
        )
        provider.download(video_uri, target)
        duration = _validate_generated_video(target)
        completed_at = _now()
        analysis = dict(project.get("analysis") or {})
        notes = list(analysis.get("notes") or [])
        notes.append("Vídeo gerado por IA com Google Veo e salvo no projeto do usuário.")
        analysis.update(
            {
                "source_duration": round(duration, 3),
                "edited_duration": round(duration, 3),
                "removed_seconds": 0,
                "ai_video": {
                    "provider": "google_veo",
                    "model_mode": generation.get("model_mode"),
                    "aspect_ratio": generation.get("aspect_ratio"),
                    "resolution": generation.get("resolution"),
                    "duration_seconds": round(duration, 3),
                },
                "notes": notes,
            }
        )
        _set_ai_video_state(
            user_id,
            project_id,
            status="uploaded",
            progress=100,
            generation_patch={
                "status": "completed",
                "completed_at": completed_at,
                "error_code": None,
                "error_message": None,
            },
            analysis=analysis,
            preview_url=f"/api/media/editor-projects/{project_id}/{target.name}",
            updated_at=completed_at,
        )
        logger.info(
            "ai_video_generation_completed",
            extra={
                "project_id": project_id,
                "user_id": user_id,
                "provider": "google_veo",
                "duration": round(duration, 3),
            },
        )
    except AiVideoProviderError as exc:
        _set_ai_video_state(
            user_id,
            project_id,
            status="failed",
            progress=100,
            generation_patch={"status": "failed", "error_code": exc.code, "error_message": str(exc)},
            error=str(exc),
            updated_at=_now(),
        )
        logger.warning(
            "ai_video_generation_failed",
            extra={"project_id": project_id, "user_id": user_id, "provider": "google_veo", "error_code": exc.code},
        )
        raise
    except Exception as exc:
        _set_ai_video_state(
            user_id,
            project_id,
            status="failed",
            progress=100,
            generation_patch={"status": "failed", "error_code": exc.__class__.__name__, "error_message": "Falha inesperada na geração."},
            error="Não foi possível concluir a geração. Tente novamente.",
            updated_at=_now(),
        )
        logger.exception(
            "ai_video_generation_unexpected_failure",
            extra={"project_id": project_id, "user_id": user_id, "provider": "google_veo"},
        )
        raise


def cancel_ai_video_project(user_id: int, project_id: str) -> dict[str, Any]:
    project = editor_ai.read_project(user_id, project_id)
    if project.get("status") not in AI_VIDEO_WORKING_STATUSES:
        return project
    generation = project.get("ai_video_generation") or {}
    if generation.get("provider_operation_id"):
        raise RuntimeError("A geração já foi enviada ao provedor e não pode ser cancelada com segurança agora.")
    return _set_ai_video_state(
        user_id,
        project_id,
        status="cancelled",
        progress=100,
        generation_patch={"status": "cancelled", "completed_at": _now()},
        updated_at=_now(),
    )
