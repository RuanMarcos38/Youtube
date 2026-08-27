from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from uuid import uuid4

from openai import OpenAI
from pydantic import BaseModel, Field

from ..config import settings
from .ffmpeg_service import ensure_ffmpeg, extract_audio_chunks, get_duration
from .transcription import transcribe_chunks


ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mpeg", ".mpg", ".webm"}
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
AI_VIDEO_QUEUED_STATUS = "ai_video_queued"
AI_VIDEO_WORKING_STATUSES = {
    "ai_video_submitted",
    "ai_video_processing",
    "ai_video_downloading",
}

PRESETS: dict[str, dict[str, Any]] = {
    "tiktok_shop_sales": {
        "label": "TikTok Shop Vendas",
        "max_shot_seconds": 3.2,
        "silence_seconds": 0.32,
        "caption_style": "impact",
        "description": "Ritmo rápido, legenda forte, zona segura e acabamento 9:16 para venda.",
    },
    "ugc_sales": {
        "label": "UGC Conversão",
        "max_shot_seconds": 4.2,
        "silence_seconds": 0.42,
        "caption_style": "ugc",
        "description": "Natural, humano e direto, com cortes limpos e foco na fala.",
    },
    "cinematic_product": {
        "label": "Produto Cinematográfico",
        "max_shot_seconds": 5.5,
        "silence_seconds": 0.55,
        "caption_style": "cinematic",
        "description": "Cortes mais elegantes, tratamento visual suave e legendas discretas.",
    },
    "fast_retention": {
        "label": "Retenção Máxima",
        "max_shot_seconds": 2.4,
        "silence_seconds": 0.28,
        "caption_style": "impact",
        "description": "Jump cuts rápidos e legendas de alto contraste para retenção.",
    },
}


class RemoveRange(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    reason: str = ""


class EditPlan(BaseModel):
    remove_ranges: list[RemoveRange] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    hook: str = ""
    notes: list[str] = Field(default_factory=list, max_length=20)


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Executável não encontrado: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "Falha no processamento de vídeo")[-6000:]
        raise RuntimeError(detail) from exc


def _project_root(user_id: int) -> Path:
    root = settings.data_path / "users" / str(user_id) / "editor-projects"
    root.mkdir(parents=True, exist_ok=True)
    return root


def project_dir(user_id: int, project_id: str) -> Path:
    target = (_project_root(user_id) / project_id).resolve()
    root = _project_root(user_id).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("Projeto inválido") from exc
    return target


def _project_file(user_id: int, project_id: str) -> Path:
    return project_dir(user_id, project_id) / "project.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def read_project(user_id: int, project_id: str) -> dict[str, Any]:
    path = _project_file(user_id, project_id)
    if not path.is_file():
        raise FileNotFoundError("Projeto não encontrado")
    return json.loads(path.read_text(encoding="utf-8"))


def list_projects(user_id: int) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for path in _project_root(user_id).glob("*/project.json"):
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items[:50]


def create_project_record(
    *,
    user_id: int,
    tenant_id: int,
    original_filename: str,
    stored_filename: str,
    preset: str,
    target_platform: str,
    created_at: str,
) -> dict[str, Any]:
    project_id = uuid4().hex
    root = project_dir(user_id, project_id)
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": project_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "original_filename": original_filename,
        "source_filename": stored_filename,
        "preset": preset if preset in PRESETS else "tiktok_shop_sales",
        "target_platform": target_platform or "tiktok_shop",
        "status": "uploaded",
        "progress": 0,
        "error": None,
        "timeline": None,
        "preview_url": None,
        "export_url": None,
        "analysis": {},
        "created_at": created_at,
        "updated_at": created_at,
    }
    _write_json(root / "project.json", payload)
    return payload


def save_project(user_id: int, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    _write_json(_project_file(user_id, project_id), payload)
    return payload


def queue_auto_edit(user_id: int, project_id: str, preset: str, updated_at: str) -> dict[str, Any]:
    project = read_project(user_id, project_id)
    if preset in PRESETS:
        project["preset"] = preset
    project["status"] = "queued"
    project["progress"] = 1
    project["error"] = None
    project["updated_at"] = updated_at
    return save_project(user_id, project_id, project)


def queue_export(user_id: int, project_id: str, updated_at: str) -> dict[str, Any]:
    project = read_project(user_id, project_id)
    if project.get("status") not in {"ready", "exported"}:
        raise ValueError("O vídeo precisa estar pronto antes da exportação.")
    project["status"] = "export_queued"
    project["progress"] = 95
    project["error"] = None
    project["updated_at"] = updated_at
    return save_project(user_id, project_id, project)


def save_timeline(user_id: int, project_id: str, timeline: dict[str, Any], updated_at: str) -> dict[str, Any]:
    project = read_project(user_id, project_id)
    if project.get("status") not in {"ready", "exported"}:
        raise ValueError("A timeline só pode ser alterada depois da edição automática.")
    project["timeline"] = timeline
    project["status"] = "queued"
    project["progress"] = 70
    project["error"] = None
    project["updated_at"] = updated_at
    return save_project(user_id, project_id, project)


def _set_project_state(user_id: int, project_id: str, *, status: str, progress: int, error: str | None = None, **extra: Any) -> None:
    project = read_project(user_id, project_id)
    project["status"] = status
    project["progress"] = max(0, min(100, int(progress)))
    project["error"] = error
    project.update(extra)
    _write_json(_project_file(user_id, project_id), project)


def claim_next_editor_task() -> tuple[int, str, str] | None:
    users_root = settings.data_path / "users"
    if not users_root.exists():
        return None
    candidates: list[tuple[float, Path]] = []
    for path in users_root.glob("*/editor-projects/*/project.json"):
        try:
            stat = path.stat()
            candidates.append((stat.st_mtime, path))
        except OSError:
            continue
    for _, path in sorted(candidates, key=lambda item: item[0]):
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
            current_status = project.get("status")
            if current_status not in {"queued", "export_queued", AI_VIDEO_QUEUED_STATUS, *AI_VIDEO_WORKING_STATUSES}:
                continue
            user_id = int(project["user_id"])
            project_id = str(project["id"])
            if current_status == "export_queued":
                mode = "export"
                project["status"] = "exporting"
                project["progress"] = 96
            elif current_status in {AI_VIDEO_QUEUED_STATUS, *AI_VIDEO_WORKING_STATUSES}:
                mode = "ai_video"
                project["status"] = "ai_video_processing"
                project["progress"] = max(5, int(project.get("progress") or 1))
            else:
                mode = "edit"
                project["status"] = "analyzing"
                project["progress"] = 5
            project["error"] = None
            _write_json(path, project)
            return user_id, project_id, mode
        except Exception:
            continue
    return None


def _detect_silence(video_path: Path, silence_seconds: float) -> list[tuple[float, float]]:
    command = [
        settings.ffmpeg_binary,
        "-hide_banner",
        "-i",
        str(video_path),
        "-af",
        f"silencedetect=noise=-36dB:d={silence_seconds:.2f}",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        return []
    text = result.stderr or ""
    starts = [float(value) for value in re.findall(r"silence_start:\s*([0-9.]+)", text)]
    ends = [float(value) for value in re.findall(r"silence_end:\s*([0-9.]+)", text)]
    return [(start, end) for start, end in zip(starts, ends) if end > start]


def _ai_plan(segments: list[dict[str, Any]], duration: float, source_name: str) -> EditPlan:
    if not settings.openai_api_key:
        return EditPlan(notes=["OPENAI_API_KEY ausente: aplicada edição automática por ritmo e silêncio."])
    transcript = "\n".join(
        f"[{float(item.get('start', 0)):.2f}-{float(item.get('end', 0)):.2f}] {str(item.get('text', '')).strip()}"
        for item in segments
        if str(item.get("text", "")).strip()
    )[: settings.max_transcript_chars]
    if not transcript:
        return EditPlan(notes=["Sem transcrição utilizável; edição baseada em áudio e ritmo."])

    client = OpenAI(api_key=settings.openai_api_key)
    system = (
        "Você é um editor sênior de vídeos de performance para TikTok Shop e social commerce. "
        "Analise a transcrição com timestamps e indique SOMENTE trechos que podem ser removidos sem perder a mensagem: "
        "retomadas/repetições óbvias, erros de gravação, frases abandonadas, enrolação e pausas verbais sem valor. "
        "Nunca remova alegações importantes do produto. Gere também palavras-chave curtas que merecem destaque nas legendas. "
        "Os intervalos devem respeitar exatamente os timestamps fornecidos."
    )
    user = f"Arquivo: {source_name}\nDuração: {duration:.2f}s\n\nTRANSCRIÇÃO:\n{transcript}"
    try:
        response = client.responses.parse(
            model=settings.openai_text_model,
            input=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            text_format=EditPlan,
        )
        return response.output_parsed or EditPlan()
    except Exception as exc:
        return EditPlan(notes=[f"Planejamento IA indisponível; fallback seguro aplicado: {exc}"])


def _merge_ranges(ranges: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    normalized = sorted(
        (max(0.0, min(start, duration)), max(0.0, min(end, duration)))
        for start, end in ranges
        if end - start >= 0.12
    )
    merged: list[list[float]] = []
    for start, end in normalized:
        if end <= start:
            continue
        if not merged or start > merged[-1][1] + 0.08:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    total_removed = sum(end - start for start, end in merged)
    if duration > 0 and total_removed > duration * 0.55:
        return [tuple(item) for item in merged if (item[1] - item[0]) <= 3.0]
    return [tuple(item) for item in merged]


def _invert_ranges(remove_ranges: list[tuple[float, float]], duration: float) -> list[tuple[float, float]]:
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for start, end in remove_ranges:
        if start > cursor + 0.15:
            keep.append((cursor, start))
        cursor = max(cursor, end)
    if duration > cursor + 0.15:
        keep.append((cursor, duration))
    return keep or [(0.0, duration)]


def _split_for_rhythm(keep_ranges: list[tuple[float, float]], transcript: list[dict[str, Any]], max_shot: float) -> list[tuple[float, float]]:
    boundaries = sorted(
        {
            round(float(item.get("end", 0.0)), 3)
            for item in transcript
            if float(item.get("end", 0.0)) > 0
        }
    )
    result: list[tuple[float, float]] = []
    for start, end in keep_ranges:
        cursor = start
        while end - cursor > max_shot + 0.4:
            target = cursor + max_shot
            options = [b for b in boundaries if cursor + 0.8 <= b <= min(end - 0.25, target + 0.8)]
            cut = min(options, key=lambda b: abs(b - target)) if options else min(end, target)
            if cut <= cursor + 0.2:
                break
            result.append((cursor, cut))
            cursor = cut
        if end - cursor > 0.2:
            result.append((cursor, end))
    return result


def _remap_captions(
    transcript: list[dict[str, Any]],
    keep_ranges: list[tuple[float, float]],
    keywords: list[str],
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    offset = 0.0
    lowered_keywords = {word.strip().lower() for word in keywords if word.strip()}
    for keep_start, keep_end in keep_ranges:
        for segment in transcript:
            start = float(segment.get("start", 0.0))
            end = float(segment.get("end", 0.0))
            text = str(segment.get("text", "")).strip()
            if not text or end <= keep_start or start >= keep_end:
                continue
            local_start = offset + max(start, keep_start) - keep_start
            local_end = offset + min(end, keep_end) - keep_start
            words = re.findall(r"[\wÀ-ÿ'-]+", text.lower())
            highlighted = [word for word in words if word in lowered_keywords]
            output.append(
                {
                    "start": round(local_start, 3),
                    "end": round(max(local_start + 0.08, local_end), 3),
                    "text": text,
                    "highlighted_words": highlighted[:4],
                }
            )
        offset += keep_end - keep_start
    return output


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, rem = divmod(centiseconds, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _write_ass(captions: list[dict[str, Any]], output_path: Path, style: str) -> Path:
    if style == "cinematic":
        primary, accent, fontsize, margin_v = "&H00FFFFFF", "&H00E8E8E8", 72, 180
    elif style == "ugc":
        primary, accent, fontsize, margin_v = "&H00FFFFFF", "&H0000E8FF", 76, 190
    else:
        primary, accent, fontsize, margin_v = "&H00FFFFFF", "&H0000FFB8", 82, 190

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Default,Arial,{fontsize},{primary},{accent},&H00101010,&H70000000,-1,0,0,0,100,100,0,0,1,5,1,2,85,85,{margin_v},1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [header]
    for caption in captions:
        text = _ass_escape(str(caption.get("text") or "").strip())
        if not text:
            continue
        for word in caption.get("highlighted_words") or []:
            pattern = re.compile(re.escape(str(word)), re.IGNORECASE)
            text = pattern.sub(lambda match: r"{\c&H00FFB8&}" + match.group(0).upper() + r"{\c&HFFFFFF&}", text, count=1)
        animated = r"{\fad(70,90)\fscx106\fscy106\t(0,120,\fscx100\fscy100)}" + text
        lines.append(
            f"Dialogue: 0,{_ass_time(float(caption['start']))},{_ass_time(float(caption['end']))},Default,,0,0,0,,{animated}\n"
        )
    output_path.write_text("".join(lines), encoding="utf-8")
    return output_path


def _escape_filter_path(path: Path) -> str:
    value = path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")
    return value


def _has_audio(source: Path) -> bool:
    try:
        result = _run(
            [
                settings.ffprobe_binary,
                "-v",
                "error",
                "-select_streams",
                "a",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                str(source),
            ]
        )
        return bool((result.stdout or "").strip())
    except Exception:
        return False


def _render_timeline(source: Path, output: Path, keep_ranges: list[tuple[float, float]], ass_path: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if not keep_ranges:
        raise RuntimeError("Timeline sem trechos ativos.")

    has_audio = _has_audio(source)
    total_duration = sum(max(0.08, end - start) for start, end in keep_ranges)
    chains: list[str] = []
    concat_inputs: list[str] = []
    audio_label = "0:a" if has_audio else "1:a"

    for index, (start, end) in enumerate(keep_ranges):
        duration = max(0.08, end - start)
        chains.append(
            f"[0:v]trim=start={start:.3f}:duration={duration:.3f},setpts=PTS-STARTPTS,"
            f"scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2,"
            f"hqdn3d=1.2:1.2:6:6,eq=contrast=1.03:saturation=1.04[v{index}]"
        )
        audio_start = start if has_audio else 0.0
        chains.append(
            f"[{audio_label}]atrim=start={audio_start:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS,"
            f"highpass=f=80,alimiter=limit=0.95[a{index}]"
        )
        concat_inputs.append(f"[v{index}][a{index}]")

    chains.append("".join(concat_inputs) + f"concat=n={len(keep_ranges)}:v=1:a=1[vcat][acat]")
    escaped = _escape_filter_path(ass_path)
    chains.append(f"[vcat]subtitles='{escaped}'[vout]")
    chains.append("[acat]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")

    command = [settings.ffmpeg_binary, "-y", "-i", str(source)]
    if not has_audio:
        command.extend(
            [
                "-f",
                "lavfi",
                "-t",
                f"{total_duration:.3f}",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
    command.extend(
        [
            "-filter_complex",
            ";".join(chains),
            "-map",
            "[vout]",
            "-map",
            "[aout]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-profile:v",
            "high",
            "-level",
            "4.1",
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    _run(command)


def _build_timeline(
    keep_ranges: list[tuple[float, float]],
    captions: list[dict[str, Any]],
    preset: str,
    source_filename: str,
) -> dict[str, Any]:
    video_clips: list[dict[str, Any]] = []
    output_cursor = 0.0
    for index, (start, end) in enumerate(keep_ranges, start=1):
        duration = end - start
        video_clips.append(
            {
                "id": f"v{index}",
                "source": source_filename,
                "source_in": round(start, 3),
                "source_out": round(end, 3),
                "timeline_in": round(output_cursor, 3),
                "timeline_out": round(output_cursor + duration, 3),
                "enabled": True,
            }
        )
        output_cursor += duration

    return {
        "version": 1,
        "canvas": {"width": 1080, "height": 1920, "fps": 30, "aspect_ratio": "9:16"},
        "preset": preset,
        "duration": round(output_cursor, 3),
        "tracks": [
            {"id": "video-main", "type": "video", "locked": False, "items": video_clips},
            {"id": "audio-main", "type": "audio", "locked": False, "items": video_clips},
            {"id": "captions", "type": "captions", "locked": False, "items": captions},
            {
                "id": "effects",
                "type": "effects",
                "locked": False,
                "items": [
                    {"type": "color_correction", "enabled": True, "mode": "adaptive"},
                    {"type": "noise_reduction", "enabled": True, "mode": "light"},
                    {"type": "audio_master", "enabled": True, "target_lufs": -14},
                    {"type": "upscale", "enabled": True, "mode": "lanczos_1080x1920"},
                ],
            },
        ],
    }


def _ranges_from_timeline(timeline: dict[str, Any]) -> list[tuple[float, float]]:
    for track in timeline.get("tracks") or []:
        if track.get("type") != "video":
            continue
        result: list[tuple[float, float]] = []
        for item in track.get("items") or []:
            if item.get("enabled", True) is False:
                continue
            start = float(item.get("source_in", 0.0))
            end = float(item.get("source_out", 0.0))
            if end > start:
                result.append((start, end))
        if result:
            return result
    return []


def process_editor_project(user_id: int, project_id: str) -> None:
    root = project_dir(user_id, project_id)
    project = read_project(user_id, project_id)
    source = root / str(project["source_filename"])
    if not source.is_file():
        raise FileNotFoundError("Vídeo enviado não encontrado.")

    try:
        _set_project_state(user_id, project_id, status="analyzing", progress=8)
        ensure_ffmpeg()
        duration = get_duration(source)

        _set_project_state(user_id, project_id, status="transcribing", progress=25)
        audio_dir = root / "audio"
        shutil.rmtree(audio_dir, ignore_errors=True)
        audio_files = extract_audio_chunks(source, audio_dir)
        transcript_text, transcript = transcribe_chunks(audio_files)
        (root / "transcript.txt").write_text(transcript_text, encoding="utf-8")
        _write_json(root / "transcript.json", {"segments": transcript})

        preset_key = str(project.get("preset") or "tiktok_shop_sales")
        selected_preset = PRESETS.get(preset_key, PRESETS["tiktok_shop_sales"])

        _set_project_state(user_id, project_id, status="ai_editing", progress=48)
        silence = _detect_silence(source, float(selected_preset["silence_seconds"]))
        ai_plan = _ai_plan(transcript, duration, str(project.get("original_filename") or source.name))
        ai_ranges = [(item.start, item.end) for item in ai_plan.remove_ranges]
        removal = _merge_ranges(silence + ai_ranges, duration)

        existing_timeline = project.get("timeline")
        if existing_timeline:
            keep = _ranges_from_timeline(existing_timeline)
        else:
            keep = _invert_ranges(removal, duration)
            keep = _split_for_rhythm(keep, transcript, float(selected_preset["max_shot_seconds"]))

        captions = _remap_captions(transcript, keep, ai_plan.keywords)
        timeline = _build_timeline(keep, captions, preset_key, source.name)
        _write_json(root / "timeline.json", timeline)

        ass_path = _write_ass(captions, root / "captions.ass", str(selected_preset["caption_style"]))
        _set_project_state(user_id, project_id, status="rendering", progress=72, timeline=timeline)

        preview = root / "preview.mp4"
        _render_timeline(source, preview, keep, ass_path)

        analysis = {
            "source_duration": round(duration, 3),
            "edited_duration": timeline["duration"],
            "removed_seconds": round(max(0.0, duration - float(timeline["duration"])), 3),
            "silence_ranges": len(silence),
            "ai_remove_ranges": [item.model_dump() for item in ai_plan.remove_ranges],
            "keywords": ai_plan.keywords,
            "hook": ai_plan.hook,
            "notes": ai_plan.notes,
            "preset": preset_key,
            "quality": {
                "resolution": "1080x1920",
                "codec": "H.264",
                "audio": "AAC 48kHz",
                "normalization": "-14 LUFS",
                "upscale": "Lanczos adaptativo",
            },
        }
        _set_project_state(
            user_id,
            project_id,
            status="ready",
            progress=100,
            timeline=timeline,
            analysis=analysis,
            preview_url=f"/api/media/editor-projects/{project_id}/preview.mp4",
        )
    except Exception as exc:
        _set_project_state(user_id, project_id, status="failed", progress=100, error=str(exc))
        raise


def export_editor_project(user_id: int, project_id: str) -> None:
    root = project_dir(user_id, project_id)
    preview = root / "preview.mp4"
    if not preview.is_file():
        raise FileNotFoundError("Preview não encontrado. Execute o Auto-Edit IA primeiro.")
    output = root / "tiktok-shop-export.mp4"
    try:
        _set_project_state(user_id, project_id, status="exporting", progress=97)
        _run(
            [
                settings.ffmpeg_binary,
                "-y",
                "-i",
                str(preview),
                "-vf",
                "scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-profile:v",
                "high",
                "-pix_fmt",
                "yuv420p",
                "-r",
                "30",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
                "-ar",
                "48000",
                "-movflags",
                "+faststart",
                str(output),
            ]
        )
        _set_project_state(
            user_id,
            project_id,
            status="exported",
            progress=100,
            export_url=f"/api/media/editor-projects/{project_id}/tiktok-shop-export.mp4",
        )
    except Exception as exc:
        _set_project_state(user_id, project_id, status="failed", progress=100, error=str(exc))
        raise


def recover_interrupted_editor_tasks() -> None:
    users_root = settings.data_path / "users"
    if not users_root.exists():
        return
    for path in users_root.glob("*/editor-projects/*/project.json"):
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
            current_status = project.get("status")
            if current_status in {"analyzing", "transcribing", "ai_editing", "rendering"}:
                project["status"] = "queued"
                project["progress"] = 1
                project["error"] = "Recovered after worker restart"
                _write_json(path, project)
            elif current_status in AI_VIDEO_WORKING_STATUSES:
                project["status"] = AI_VIDEO_QUEUED_STATUS
                project["progress"] = max(1, int(project.get("progress") or 1))
                project["error"] = "Recovered after worker restart"
                _write_json(path, project)
            elif current_status == "exporting":
                project["status"] = "export_queued"
                project["progress"] = 95
                project["error"] = "Recovered after worker restart"
                _write_json(path, project)
        except Exception:
            continue


def run_claimed_editor_task(user_id: int, project_id: str, mode: str) -> None:
    if mode == "export":
        export_editor_project(user_id, project_id)
    else:
        process_editor_project(user_id, project_id)
