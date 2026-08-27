from __future__ import annotations

import json
import logging
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from openai import OpenAI
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Clip, User
from ..schemas import ClipCaptionUpdateRequest
from ..services.billing import can_use_tool
from ..services.editor_ai import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    PRESETS,
    create_project_record,
    list_projects,
    project_dir,
    queue_auto_edit,
    queue_export,
    read_project,
    save_project,
    save_timeline,
)
from ..services.editor_ai_pro import DEFAULT_EDIT_OPTIONS, MAX_MUSIC_BYTES, MUSIC_EXTENSIONS

router = APIRouter(prefix="/editor-ai", tags=["editor-ai"])
logger = logging.getLogger(__name__)

SUPPORTED_AI_EDIT_ACTIONS = {
    "move_caption",
    "remove_caption",
    "resize_caption",
    "restore_caption_default",
    "change_music_volume",
    "remove_music",
}

CAPTION_AI_EDIT_ACTIONS = {"move_caption", "remove_caption", "resize_caption", "restore_caption_default"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutoEditRequest(BaseModel):
    preset: str = "tiktok_shop_sales"
    captions_enabled: bool = True
    caption_style: str = "auto"
    music_mode: str = "auto"
    music_mood: str = "auto"
    music_volume: float = Field(default=0.18, ge=0.0, le=0.45)
    edit_intensity: str = "high"
    auto_reframe: bool = True
    hook_variants: bool = True


class TimelineUpdateRequest(BaseModel):
    timeline: dict[str, Any] = Field(default_factory=dict)


class EditorAiEditRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1200)


class EditorAiActionPlan(BaseModel):
    action: Literal[
        "move_caption",
        "remove_caption",
        "edit_caption_text",
        "resize_caption",
        "change_caption_alignment",
        "change_caption_safe_area",
        "restore_caption_default",
        "trim_video",
        "change_music_volume",
        "remove_music",
        "change_caption_style",
        "unsupported",
    ] = "unsupported"
    target: Literal["current_video"] = "current_video"
    supported: bool = False
    reason: str = Field(default="", max_length=320)
    requires_render: bool = False
    caption_position: Literal["top", "middle", "bottom"] | None = None
    caption_margin_v: int | None = Field(default=None, ge=40, le=760)
    caption_font_size: int | None = Field(default=None, ge=14, le=32)
    captions_enabled: bool | None = None
    music_mode: Literal["auto", "none", "custom"] | None = None
    music_volume: float | None = Field(default=None, ge=0.0, le=0.45)
    preview_note: str = Field(default="", max_length=360)
    unsupported_reason: str | None = Field(default=None, max_length=360)


class EditorAiApplyRequest(BaseModel):
    plan: EditorAiActionPlan | None = None


def _normalize_edit_options(payload: AutoEditRequest) -> dict[str, Any]:
    caption_style = payload.caption_style if payload.caption_style in {"auto", "impact", "ugc", "cinematic"} else "auto"
    music_mode = payload.music_mode if payload.music_mode in {"auto", "none", "custom"} else "auto"
    music_mood = payload.music_mood if payload.music_mood in {"auto", "energetic", "confident", "elegant", "natural"} else "auto"
    edit_intensity = payload.edit_intensity if payload.edit_intensity in {"balanced", "high", "maximum"} else "high"
    return {
        "captions_enabled": bool(payload.captions_enabled),
        "caption_style": caption_style,
        "music_mode": music_mode,
        "music_mood": music_mood,
        "music_volume": max(0.0, min(0.45, float(payload.music_volume))),
        "edit_intensity": edit_intensity,
        "auto_reframe": bool(payload.auto_reframe),
        "hook_variants": bool(payload.hook_variants),
    }


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in normalized if not unicodedata.combining(char)).lower()


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default


def _caption_track_item(project: dict[str, Any]) -> dict[str, Any] | None:
    timeline = project.get("timeline") or {}
    for track in timeline.get("tracks") or []:
        if track.get("type") != "captions":
            continue
        items = track.get("items") or []
        return items[0] if items and isinstance(items[0], dict) else None
    return None


def _clip_has_subtitle(clip: Clip) -> bool:
    if not clip.subtitle_path:
        return False
    path = Path(clip.subtitle_path)
    return path.is_file() and path.stat().st_size > 0


def _caption_state(project: dict[str, Any], clip: Clip | None = None) -> dict[str, Any]:
    item = _caption_track_item(project) or {}
    options = project.get("edit_options") or {}
    analysis = (project.get("analysis") or {}).get("captions") or {}
    return {
        "enabled": _clip_has_subtitle(clip) if clip else bool(analysis.get("enabled", options.get("captions_enabled", True))),
        "position": (clip.caption_position if clip else item.get("caption_position") or options.get("caption_position") or "bottom") or "bottom",
        "margin_v": _clamp_int(clip.caption_margin_v if clip else item.get("caption_margin_v") or options.get("caption_margin_v"), 120, 40, 760),
        "font_size": _clamp_int(clip.caption_font_size if clip else item.get("caption_font_size") or options.get("caption_font_size"), 18, 14, 32),
        "style": analysis.get("style") or options.get("caption_style") or "auto",
    }


def _unsupported_ai_plan(reason: str) -> EditorAiActionPlan:
    return EditorAiActionPlan(
        action="unsupported",
        supported=False,
        requires_render=False,
        reason="Alteração fora do conjunto seguro do editor atual.",
        unsupported_reason=reason,
        preview_note=reason,
    )


def _fallback_ai_edit_plan(prompt: str, project: dict[str, Any], clip: Clip | None = None) -> EditorAiActionPlan:
    text = _fold_text(prompt)
    caption = _caption_state(project, clip)
    has_caption_context = any(token in text for token in ("legenda", "subtitle", "caption", "texto"))
    face_context = any(token in text for token in ("rosto", "face", "olho", "olhos", "boca", "nariz", "pessoa", "cobr"))

    if has_caption_context and face_context:
        return EditorAiActionPlan(
            action="move_caption",
            supported=True,
            reason="Evitar sobreposição da legenda com rosto/olhos/boca.",
            requires_render=True,
            caption_position="bottom",
            caption_margin_v=70,
            caption_font_size=caption["font_size"],
            preview_note="A legenda será recriada na área inferior segura, mantendo texto, estilo e sincronização.",
        )

    if has_caption_context and any(token in text for token in (
        "excluir",
        "remover",
        "remova",
        "apagar",
        "apague",
        "retire a legenda",
        "retire as legenda",
        "retire todas",
        "retirar legenda",
        "retirar todas",
        "sem legenda",
        "tirar legenda",
        "tirar as legenda",
        "ocultar legenda",
    )):
        return EditorAiActionPlan(
            action="remove_caption",
            supported=True,
            reason="Remover a camada de legenda do vídeo atual.",
            requires_render=True,
            captions_enabled=False,
            caption_position=caption["position"],
            caption_margin_v=caption["margin_v"],
            caption_font_size=caption["font_size"],
            preview_note="As legendas serão removidas quando houver camada/arquivo de legenda disponível.",
        )

    if has_caption_context and any(token in text for token in ("baixo", "inferior", "embaixo", "rodape")):
        return EditorAiActionPlan(
            action="move_caption",
            supported=True,
            reason="Reposicionar legenda para a área inferior segura.",
            requires_render=True,
            caption_position="bottom",
            caption_margin_v=70,
            caption_font_size=caption["font_size"],
            preview_note="A legenda será movida para baixo sem alterar texto, estilo ou sincronização.",
        )

    if has_caption_context and any(token in text for token in ("cima", "superior", "topo")):
        return EditorAiActionPlan(
            action="move_caption",
            supported=True,
            reason="Reposicionar legenda para a área superior.",
            requires_render=True,
            caption_position="top",
            caption_margin_v=140,
            caption_font_size=caption["font_size"],
            preview_note="A legenda será movida para cima usando a renderização existente.",
        )

    if has_caption_context and any(token in text for token in ("padrao", "original", "restaur")):
        return EditorAiActionPlan(
            action="restore_caption_default",
            supported=True,
            reason="Restaurar configuração padrão de legenda.",
            requires_render=True,
            caption_position="bottom",
            caption_margin_v=120,
            caption_font_size=18,
            captions_enabled=True,
            preview_note="A legenda voltará para a configuração padrão do ShortsFlow.",
        )

    if has_caption_context and any(token in text for token in ("diminu", "menor", "reduz")):
        return EditorAiActionPlan(
            action="resize_caption",
            supported=True,
            reason="Reduzir tamanho da legenda mantendo a posição atual.",
            requires_render=True,
            caption_position=caption["position"],
            caption_margin_v=caption["margin_v"],
            caption_font_size=max(14, caption["font_size"] - 4),
            preview_note="O tamanho da legenda será reduzido de forma segura.",
        )

    if has_caption_context and any(token in text for token in ("aument", "maior")):
        return EditorAiActionPlan(
            action="resize_caption",
            supported=True,
            reason="Aumentar tamanho da legenda mantendo a posição atual.",
            requires_render=True,
            caption_position=caption["position"],
            caption_margin_v=caption["margin_v"],
            caption_font_size=min(32, caption["font_size"] + 4),
            preview_note="O tamanho da legenda será aumentado dentro do limite permitido.",
        )

    if any(token in text for token in ("musica", "trilha", "audio")):
        options = project.get("edit_options") or {}
        current_volume = _clamp_float(options.get("music_volume"), 0.18, 0.0, 0.45)
        if any(token in text for token in ("retire", "remova", "remover", "sem musica", "sem trilha", "mutar musica")):
            return EditorAiActionPlan(
                action="remove_music",
                supported=True,
                reason="Desativar música no projeto do editor.",
                requires_render=False,
                music_mode="none",
                preview_note="A música será desativada nas opções do projeto.",
            )
        if any(token in text for token in ("diminu", "baix", "reduz")):
            return EditorAiActionPlan(
                action="change_music_volume",
                supported=True,
                reason="Reduzir volume da música.",
                requires_render=False,
                music_volume=max(0.0, current_volume - 0.07),
                preview_note="O volume da música será reduzido nas opções do projeto.",
            )
        if any(token in text for token in ("aument", "mais alto", "subir")):
            return EditorAiActionPlan(
                action="change_music_volume",
                supported=True,
                reason="Aumentar volume da música.",
                requires_render=False,
                music_volume=min(0.45, current_volume + 0.07),
                preview_note="O volume da música será aumentado nas opções do projeto.",
            )

    if any(token in text for token in ("corte", "cortar", "primeiros", "ultimos", "dinamico", "dinamica")):
        return _unsupported_ai_plan("Esta alteração ainda não é suportada pelo editor atual. Use a linha do tempo para ajustar cortes manualmente.")

    if has_caption_context and any(token in text for token in ("portugues", "corrija", "corrigir", "texto")):
        return _unsupported_ai_plan("Correção automática do texto da legenda ainda não está habilitada neste editor.")

    return _unsupported_ai_plan("Esta alteração ainda não é suportada pelo editor atual.")


def _ai_edit_context(project: dict[str, Any], clip: Clip | None = None) -> dict[str, Any]:
    caption = _caption_state(project, clip)
    timeline = project.get("timeline") or {}
    canvas = timeline.get("canvas") or {}
    return {
        "project_id": project.get("id"),
        "source_clip_id": project.get("source_clip_id"),
        "duration": timeline.get("duration") or (project.get("analysis") or {}).get("edited_duration"),
        "canvas": {
            "width": canvas.get("width"),
            "height": canvas.get("height"),
            "aspect_ratio": canvas.get("aspect_ratio"),
        },
        "caption": caption,
        "music": {
            "mode": (project.get("edit_options") or {}).get("music_mode"),
            "volume": (project.get("edit_options") or {}).get("music_volume"),
        },
        "supported_actions": sorted(SUPPORTED_AI_EDIT_ACTIONS),
    }


def _openai_ai_edit_plan(prompt: str, project: dict[str, Any], clip: Clip | None = None) -> EditorAiActionPlan:
    fallback = _fallback_ai_edit_plan(prompt, project, clip)
    if not settings.openai_api_key:
        return fallback

    system = (
        "Você interpreta solicitações de edição para o ShortsFlow AI. "
        "Retorne somente um plano estruturado validável. "
        "Ações executáveis agora: move_caption, remove_caption, resize_caption, restore_caption_default, change_music_volume, remove_music. "
        "Se o pedido depender de corte, correção de texto, alinhamento horizontal, mudança de estilo ou algo não listado, use action unsupported. "
        "Para pedidos como 'legenda no rosto', 'não cobrir olhos/boca' ou 'tire a legenda do rosto', escolha move_caption com caption_position bottom, caption_margin_v 70 e preserve texto, timing, fonte e estilo. "
        "Nunca solicite execução de shell, SQL, credenciais, arquivos arbitrários ou infraestrutura."
    )
    user_message = {
        "prompt": prompt,
        "context": _ai_edit_context(project, clip),
    }
    try:
        response = OpenAI(api_key=settings.openai_api_key).responses.parse(
            model=settings.openai_text_model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_message, ensure_ascii=False)},
            ],
            text_format=EditorAiActionPlan,
        )
        return response.output_parsed or fallback
    except Exception as exc:
        logger.warning(
            "editor_ai_plan_fallback",
            extra={"project_id": project.get("id"), "action": fallback.action, "error": exc.__class__.__name__},
        )
        return fallback


def _validated_ai_edit_plan(plan: EditorAiActionPlan, project: dict[str, Any], clip: Clip | None = None) -> EditorAiActionPlan:
    if plan.action not in SUPPORTED_AI_EDIT_ACTIONS:
        return _unsupported_ai_plan(plan.unsupported_reason or "Esta alteração ainda não é suportada pelo editor atual.")

    caption = _caption_state(project, clip)
    if plan.action in CAPTION_AI_EDIT_ACTIONS:
        position = plan.caption_position if plan.caption_position in {"top", "middle", "bottom"} else caption["position"]
        margin = _clamp_int(plan.caption_margin_v, caption["margin_v"], 40, 760)
        size = _clamp_int(plan.caption_font_size, caption["font_size"], 14, 32)
        if plan.action == "move_caption" and position == "middle" and any(token in _fold_text(plan.reason) for token in ("rosto", "face", "olho", "boca")):
            position, margin = "bottom", 70
        if plan.action == "remove_caption":
            return plan.model_copy(update={
                "supported": True,
                "requires_render": True,
                "captions_enabled": False,
                "caption_position": position,
                "caption_margin_v": margin,
                "caption_font_size": size,
                "preview_note": plan.preview_note or "As legendas serão removidas da nova renderização.",
            })
        if plan.action == "restore_caption_default":
            position, margin, size = "bottom", 120, 18
        return plan.model_copy(update={
            "supported": True,
            "requires_render": True,
            "caption_position": position,
            "caption_margin_v": margin,
            "caption_font_size": size,
            "captions_enabled": True,
            "preview_note": plan.preview_note or "A legenda será recriada com os parâmetros validados.",
        })

    if plan.action == "remove_music":
        return plan.model_copy(update={
            "supported": True,
            "requires_render": False,
            "music_mode": "none",
            "preview_note": plan.preview_note or "A música será desativada nas opções do projeto.",
        })

    if plan.action == "change_music_volume":
        return plan.model_copy(update={
            "supported": True,
            "requires_render": False,
            "music_volume": _clamp_float(plan.music_volume, 0.18, 0.0, 0.45),
            "preview_note": plan.preview_note or "O volume da música será ajustado nas opções do projeto.",
        })

    return _unsupported_ai_plan("Esta alteração ainda não é suportada pelo editor atual.")


def _snapshot_ai_edit_state(project: dict[str, Any], clip: Clip | None = None) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "created_at": _now(),
        "edit_options": dict(project.get("edit_options") or {}),
        "analysis_captions": dict((project.get("analysis") or {}).get("captions") or {}),
        "timeline_caption_item": dict(_caption_track_item(project) or {}),
    }
    if clip:
        subtitle_path = Path(clip.subtitle_path) if clip.subtitle_path else None
        snapshot["clip"] = {
            "id": clip.id,
            "caption_position": clip.caption_position or "bottom",
            "caption_margin_v": clip.caption_margin_v or 120,
            "caption_font_size": clip.caption_font_size or 18,
            "subtitle_srt": subtitle_path.read_text(encoding="utf-8") if subtitle_path and subtitle_path.is_file() else "",
        }
    return snapshot


def _apply_plan_to_project(project: dict[str, Any], plan: EditorAiActionPlan) -> None:
    options = dict(DEFAULT_EDIT_OPTIONS)
    options.update(project.get("edit_options") or {})

    if plan.action in CAPTION_AI_EDIT_ACTIONS:
        if plan.action == "remove_caption":
            options["captions_enabled"] = False
        else:
            options["captions_enabled"] = True
        if plan.caption_position:
            options["caption_position"] = plan.caption_position
        if plan.caption_margin_v is not None:
            options["caption_margin_v"] = plan.caption_margin_v
        if plan.caption_font_size is not None:
            options["caption_font_size"] = plan.caption_font_size

        item = _caption_track_item(project)
        if item is not None:
            if plan.caption_position:
                item["caption_position"] = plan.caption_position
            if plan.caption_margin_v is not None:
                item["caption_margin_v"] = plan.caption_margin_v
            if plan.caption_font_size is not None:
                item["caption_font_size"] = plan.caption_font_size

        analysis = dict(project.get("analysis") or {})
        captions = dict(analysis.get("captions") or {})
        captions.update({
            "enabled": plan.action != "remove_caption",
            "safe_zone": True,
            "position": plan.caption_position,
            "margin_v": plan.caption_margin_v,
            "font_size": plan.caption_font_size,
        })
        analysis["captions"] = captions
        project["analysis"] = analysis

    if plan.action == "remove_music":
        options["music_mode"] = "none"
    elif plan.action == "change_music_volume" and plan.music_volume is not None:
        options["music_volume"] = plan.music_volume

    project["edit_options"] = options


def _copy_clip_render_to_editor_project(project: dict[str, Any], clip: Clip, user_id: int, project_id: str) -> None:
    source = Path(clip.file_path)
    if not source.is_file():
        raise HTTPException(status_code=409, detail="Vídeo renderizado do corte não encontrado para atualizar o preview.")
    stored_filename = str(project.get("source_filename") or "source.mp4")
    target = project_dir(user_id, project_id) / stored_filename
    shutil.copy2(source, target)
    version = int(datetime.now(timezone.utc).timestamp())
    project["preview_url"] = f"/api/media/editor-projects/{project_id}/{stored_filename}?v={version}"


def _clip_editor_project_payload(clip: Clip, project_id: str, stored_filename: str, created_at: str) -> dict[str, Any]:
    duration = max(0.1, float(clip.end_seconds or 0) - float(clip.start_seconds or 0))
    return {
        "source_clip_id": clip.id,
        "source_job_id": clip.job_id,
        "preview_url": f"/api/media/editor-projects/{project_id}/{stored_filename}",
        "timeline": {
            "version": 1,
            "duration": round(duration, 3),
            "preset": "shorts_review",
            "canvas": {"width": 1080, "height": 1920, "fps": 30, "aspect_ratio": "9:16"},
            "tracks": [
                {
                    "id": "video-main",
                    "type": "video",
                    "items": [
                        {
                            "id": f"clip-{clip.id}",
                            "source": stored_filename,
                            "source_in": 0,
                            "source_out": round(duration, 3),
                            "timeline_in": 0,
                            "timeline_out": round(duration, 3),
                            "enabled": True,
                        }
                    ],
                },
                {
                    "id": "caption-main",
                    "type": "captions",
                    "items": [
                        {
                            "id": f"caption-{clip.id}",
                            "caption_position": clip.caption_position or "bottom",
                            "caption_margin_v": clip.caption_margin_v or 120,
                            "caption_font_size": clip.caption_font_size or 18,
                        }
                    ],
                },
            ],
        },
        "analysis": {
            "source_duration": round(duration, 3),
            "edited_duration": round(duration, 3),
            "removed_seconds": 0,
            "notes": ["Projeto criado a partir de um corte aprovado em Publicações."],
            "captions": {
                "enabled": bool(clip.subtitle_path),
                "style": "revisão",
                "safe_zone": True,
            },
        },
        "edit_options": dict(DEFAULT_EDIT_OPTIONS),
        "updated_at": created_at,
        "loaded_from_clip": {
            "clip_id": clip.id,
            "job_id": clip.job_id,
            "title": clip.title,
        },
    }


@router.get("/presets")
def presets():
    return [
        {
            "id": key,
            "label": value["label"],
            "description": value["description"],
            "target": "TikTok Shop / Reels / YouTube Shorts",
        }
        for key, value in PRESETS.items()
    ]


@router.get("/options")
def editor_options():
    return {
        "defaults": DEFAULT_EDIT_OPTIONS,
        "caption_styles": [
            {"id": "auto", "label": "Automática pela IA"},
            {"id": "impact", "label": "Impacto / Performance"},
            {"id": "ugc", "label": "UGC / Natural"},
            {"id": "cinematic", "label": "Cinematográfica"},
        ],
        "music_modes": [
            {"id": "auto", "label": "Trilha automática"},
            {"id": "custom", "label": "Minha música"},
            {"id": "none", "label": "Sem música"},
        ],
        "music_moods": [
            {"id": "auto", "label": "IA decide"},
            {"id": "energetic", "label": "Energética"},
            {"id": "confident", "label": "Confiante"},
            {"id": "elegant", "label": "Elegante"},
            {"id": "natural", "label": "Natural"},
        ],
        "edit_intensities": [
            {"id": "balanced", "label": "Equilibrada"},
            {"id": "high", "label": "Alta performance"},
            {"id": "maximum", "label": "Máxima retenção"},
        ],
    }


@router.get("/projects")
def projects(user: User = Depends(get_current_user)):
    return list_projects(user.id)


@router.get("/projects/{project_id}")
def project(project_id: str, user: User = Depends(get_current_user)):
    try:
        return read_project(user.id, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc


def _project_source_clip(project: dict[str, Any], user: User, db: Session) -> Clip | None:
    raw_clip_id = project.get("source_clip_id") or (project.get("loaded_from_clip") or {}).get("clip_id")
    try:
        clip_id = int(raw_clip_id or 0)
    except (TypeError, ValueError):
        return None
    if clip_id <= 0:
        return None
    return db.query(Clip).filter(Clip.id == clip_id, Clip.user_id == user.id).first()


@router.post("/projects/{project_id}/ai-edit-plan", response_model=EditorAiActionPlan)
def create_ai_edit_plan(
    project_id: str,
    payload: EditorAiEditRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        current = read_project(user.id, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc

    clip = _project_source_clip(current, user, db)
    plan = _validated_ai_edit_plan(_openai_ai_edit_plan(payload.prompt.strip(), current, clip), current, clip)
    current["pending_ai_edit"] = plan.model_dump(mode="json")
    current["updated_at"] = _now()
    save_project(user.id, project_id, current)
    logger.info(
        "editor_ai_plan_created",
        extra={"project_id": project_id, "clip_id": current.get("source_clip_id"), "ai_action": plan.action, "supported": plan.supported},
    )
    return plan


@router.post("/projects/{project_id}/ai-edit-apply")
def apply_ai_edit_to_project(
    project_id: str,
    payload: EditorAiApplyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        current = read_project(user.id, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc

    raw_plan = payload.plan or current.get("pending_ai_edit")
    if not raw_plan:
        raise HTTPException(status_code=400, detail="Nenhuma alteração de IA foi preparada para aplicar.")
    plan = raw_plan if isinstance(raw_plan, EditorAiActionPlan) else EditorAiActionPlan.model_validate(raw_plan)
    clip = _project_source_clip(current, user, db)
    plan = _validated_ai_edit_plan(plan, current, clip)
    if not plan.supported:
        raise HTTPException(status_code=409, detail=plan.unsupported_reason or "Esta alteração ainda não é suportada pelo editor atual.")

    snapshot = _snapshot_ai_edit_state(current, clip)
    _apply_plan_to_project(current, plan)

    if plan.action in CAPTION_AI_EDIT_ACTIONS and clip:
        caption = _caption_state(current, clip)
        caption_payload = ClipCaptionUpdateRequest(
            caption_position=plan.caption_position or caption["position"],
            caption_margin_v=plan.caption_margin_v or caption["margin_v"],
            caption_font_size=plan.caption_font_size or caption["font_size"],
            subtitle_srt="" if plan.action == "remove_caption" else None,
        )
        from .clips import update_clip_captions

        update_clip_captions(clip.id, caption_payload, user=user, db=db)
        db.refresh(clip)
        _copy_clip_render_to_editor_project(current, clip, user.id, project_id)

    history = list(current.get("ai_edit_history") or [])
    history.append({
        "created_at": _now(),
        "action": plan.action,
        "reason": plan.reason,
        "requires_render": plan.requires_render,
        "source_clip_id": current.get("source_clip_id"),
    })
    current["ai_edit_history"] = history[-10:]
    current["last_ai_edit_snapshot"] = snapshot
    current.pop("pending_ai_edit", None)
    current["status"] = "ready"
    current["progress"] = 100
    current["updated_at"] = _now()
    logger.info(
        "editor_ai_plan_applied",
        extra={"project_id": project_id, "clip_id": current.get("source_clip_id"), "ai_action": plan.action},
    )
    return save_project(user.id, project_id, current)


@router.post("/projects/{project_id}/ai-edit-undo")
def undo_last_ai_edit(
    project_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        current = read_project(user.id, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc

    snapshot = current.get("last_ai_edit_snapshot")
    if not isinstance(snapshot, dict):
        raise HTTPException(status_code=409, detail="Nenhuma alteração de IA disponível para desfazer.")

    current["edit_options"] = dict(snapshot.get("edit_options") or DEFAULT_EDIT_OPTIONS)
    analysis = dict(current.get("analysis") or {})
    analysis["captions"] = dict(snapshot.get("analysis_captions") or {})
    current["analysis"] = analysis
    item = _caption_track_item(current)
    previous_item = snapshot.get("timeline_caption_item") or {}
    if item is not None and isinstance(previous_item, dict) and previous_item:
        item.clear()
        item.update(previous_item)

    clip_snapshot = snapshot.get("clip") or {}
    clip = None
    try:
        clip_id = int(clip_snapshot.get("id") or 0)
    except (TypeError, ValueError):
        clip_id = 0
    if clip_id > 0:
        clip = db.query(Clip).filter(Clip.id == clip_id, Clip.user_id == user.id).first()
    if clip:
        caption_payload = ClipCaptionUpdateRequest(
            caption_position=clip_snapshot.get("caption_position") or "bottom",
            caption_margin_v=clip_snapshot.get("caption_margin_v") or 120,
            caption_font_size=clip_snapshot.get("caption_font_size") or 18,
            subtitle_srt=clip_snapshot.get("subtitle_srt", ""),
        )
        from .clips import update_clip_captions

        update_clip_captions(clip.id, caption_payload, user=user, db=db)
        db.refresh(clip)
        _copy_clip_render_to_editor_project(current, clip, user.id, project_id)

    current.pop("last_ai_edit_snapshot", None)
    current.pop("pending_ai_edit", None)
    current["status"] = "ready"
    current["progress"] = 100
    current["updated_at"] = _now()
    logger.info("editor_ai_undo", extra={"project_id": project_id, "clip_id": clip_id or None})
    return save_project(user.id, project_id, current)


@router.post("/clips/{clip_id}/project", status_code=status.HTTP_201_CREATED)
def create_project_from_clip(
    clip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    clip = db.query(Clip).filter(Clip.id == clip_id, Clip.user_id == user.id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Corte não encontrado.")

    source = Path(clip.file_path)
    if not source.is_file():
        raise HTTPException(status_code=404, detail="Arquivo do corte não encontrado para edição.")

    for item in list_projects(user.id):
        if int(item.get("source_clip_id") or 0) != clip.id:
            continue
        project_id = str(item.get("id") or "")
        stored_filename = str(item.get("source_filename") or "")
        if not project_id:
            continue
        try:
            existing = read_project(user.id, project_id)
            if stored_filename and (project_dir(user.id, project_id) / stored_filename).is_file():
                return existing
        except (FileNotFoundError, ValueError):
            continue

    extension = source.suffix.lower() if source.suffix.lower() in ALLOWED_EXTENSIONS else ".mp4"
    stored_filename = f"source{extension}"
    created_at = _now()
    project = create_project_record(
        user_id=user.id,
        tenant_id=user.tenant_id,
        original_filename=f"ShortsFlow corte #{clip.id}{extension}",
        stored_filename=stored_filename,
        preset="fast_retention",
        target_platform="youtube_shorts",
        created_at=created_at,
    )
    root = project_dir(user.id, project["id"])
    shutil.copy2(source, root / stored_filename)
    project.update(_clip_editor_project_payload(clip, project["id"], stored_filename, created_at))
    project["status"] = "ready"
    project["progress"] = 100
    return save_project(user.id, project["id"], project)


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: UploadFile = File(...),
    preset: str = Form("tiktok_shop_sales"),
    target_platform: str = Form("all_social"),
    rights_confirmed: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not rights_confirmed:
        raise HTTPException(status_code=400, detail="Confirme que você possui direitos, licença ou autorização para editar e publicar este vídeo.")

    allowed, reason = can_use_tool(db, user)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)

    original_name = Path(file.filename or "video.mp4").name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Formato não suportado. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}.")

    chosen_preset = preset if preset in PRESETS else "tiktok_shop_sales"
    stored_filename = f"source{extension}"
    project = create_project_record(
        user_id=user.id,
        tenant_id=user.tenant_id,
        original_filename=original_name,
        stored_filename=stored_filename,
        preset=chosen_preset,
        target_platform=target_platform,
        created_at=_now(),
    )
    project["edit_options"] = dict(DEFAULT_EDIT_OPTIONS)
    root = project_dir(user.id, project["id"])
    target = root / stored_filename

    total = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="O vídeo excede o limite de 500 MB.")
                output.write(chunk)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    finally:
        await file.close()

    project["upload_bytes"] = total
    save_project(user.id, project["id"], project)
    return project


@router.post("/projects/{project_id}/music")
async def upload_music(
    project_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    try:
        project = read_project(user.id, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc

    original_name = Path(file.filename or "music.mp3").name
    extension = Path(original_name).suffix.lower()
    if extension not in MUSIC_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Formato de áudio não suportado. Use: {', '.join(sorted(MUSIC_EXTENSIONS))}.")

    root = project_dir(user.id, project_id)
    stored_name = f"custom-music{extension}"
    target = root / stored_name
    total = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = await file.read(512 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_MUSIC_BYTES:
                    target.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="A música excede o limite de 50 MB.")
                output.write(chunk)
    finally:
        await file.close()

    project["custom_music_filename"] = stored_name
    project["custom_music_original_name"] = original_name
    project["updated_at"] = _now()
    save_project(user.id, project_id, project)
    return project


@router.post("/projects/{project_id}/auto-edit", status_code=status.HTTP_202_ACCEPTED)
def auto_edit(
    project_id: str,
    payload: AutoEditRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed, reason = can_use_tool(db, user)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)
    try:
        current = read_project(user.id, project_id)
        edit_options = _normalize_edit_options(payload)
        if edit_options["music_mode"] == "custom" and not current.get("custom_music_filename"):
            raise HTTPException(status_code=409, detail="Selecione e envie uma música antes de iniciar a edição com música própria.")
        queued = queue_auto_edit(user.id, project_id, payload.preset, _now())
        queued["edit_options"] = edit_options
        save_project(user.id, project_id, queued)
        return queued
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc


@router.put("/projects/{project_id}/timeline", status_code=status.HTTP_202_ACCEPTED)
def update_timeline(
    project_id: str,
    payload: TimelineUpdateRequest,
    user: User = Depends(get_current_user),
):
    try:
        return save_timeline(user.id, project_id, payload.timeline, _now())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/projects/{project_id}/export/tiktok-shop", status_code=status.HTTP_202_ACCEPTED)
def export_social_ready(project_id: str, user: User = Depends(get_current_user)):
    try:
        return queue_export(user.id, project_id, _now())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
