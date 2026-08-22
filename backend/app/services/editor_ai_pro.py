from __future__ import annotations

import json
import math
import re
import subprocess
import wave
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field

from ..config import settings
from . import editor_ai as base

try:  # Optional at import time so a missing OpenCV wheel never breaks the core editor.
    import cv2  # type: ignore
except Exception:  # pragma: no cover - safe runtime fallback
    cv2 = None


class CreativeFinishPlan(BaseModel):
    mood: str = "energetic"
    hook_variants: list[str] = Field(default_factory=list, max_length=3)
    broll_concepts: list[str] = Field(default_factory=list, max_length=6)


MOOD_AUDIO = {
    "energetic": {"bed_hz": 116.0, "pulse_hz": 232.0, "accent_hz": 520.0},
    "confident": {"bed_hz": 98.0, "pulse_hz": 196.0, "accent_hz": 440.0},
    "elegant": {"bed_hz": 82.4, "pulse_hz": 164.8, "accent_hz": 392.0},
    "natural": {"bed_hz": 73.4, "pulse_hz": 146.8, "accent_hz": 349.2},
}


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Executável não encontrado: {command[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "Falha no acabamento audiovisual")[-6000:]
        raise RuntimeError(detail) from exc


def _safe_text(value: str, limit: int = 76) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip()
    return cleaned[:limit].rstrip(" ,.;:-")


def _load_transcript(root: Path) -> list[dict[str, Any]]:
    path = root / "transcript.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return list(payload.get("segments") or [])
    except Exception:
        return []


def _fallback_hooks(project: dict[str, Any], timeline: dict[str, Any]) -> list[str]:
    captions: list[dict[str, Any]] = []
    for track in timeline.get("tracks") or []:
        if track.get("type") == "captions":
            captions = list(track.get("items") or [])
            break
    first_line = _safe_text(str((captions[0] if captions else {}).get("text") or ""), 58)
    source = _safe_text(str(project.get("original_filename") or "produto"), 42)
    candidates = [
        first_line or f"Olha isso antes de escolher {source}",
        f"O detalhe que muda tudo em {source}",
        f"Veja por que isso chama atenção em segundos",
    ]
    result: list[str] = []
    for item in candidates:
        item = _safe_text(item, 64)
        if item and item.lower() not in {value.lower() for value in result}:
            result.append(item)
    return result[:3]


def _creative_finish_plan(
    project: dict[str, Any], transcript: list[dict[str, Any]], timeline: dict[str, Any]
) -> CreativeFinishPlan:
    fallback = CreativeFinishPlan(
        mood="energetic" if str(project.get("preset")) in {"tiktok_shop_sales", "fast_retention"} else "natural",
        hook_variants=_fallback_hooks(project, timeline),
        broll_concepts=list((project.get("analysis") or {}).get("keywords") or [])[:4],
    )
    if not settings.openai_api_key:
        return fallback

    transcript_text = "\n".join(
        f"[{float(item.get('start', 0)):.2f}-{float(item.get('end', 0)):.2f}] {str(item.get('text', '')).strip()}"
        for item in transcript
        if str(item.get("text", "")).strip()
    )[:30000]
    if not transcript_text:
        return fallback

    client = OpenAI(api_key=settings.openai_api_key)
    system = (
        "Você é diretor criativo sênior de anúncios verticais para TikTok Shop, Reels e YouTube Shorts. "
        "Crie exatamente 3 ganchos curtos para os primeiros 3 segundos, sem inventar preço, prova, benefício ou promessa. "
        "Cada gancho deve ser fiel ao conteúdo, diferente dos demais e ter no máximo 64 caracteres. "
        "Escolha um mood entre energetic, confident, elegant ou natural. "
        "Liste também até 6 conceitos curtos de B-roll que possam ser ilustrados usando apenas o próprio material do usuário."
    )
    user = (
        f"Preset: {project.get('preset')}\nArquivo: {project.get('original_filename')}\n\n"
        f"TRANSCRIÇÃO:\n{transcript_text}"
    )
    try:
        response = client.responses.parse(
            model=settings.openai_text_model,
            input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            text_format=CreativeFinishPlan,
        )
        parsed = response.output_parsed or fallback
        mood = parsed.mood if parsed.mood in MOOD_AUDIO else fallback.mood
        hooks = [_safe_text(value, 64) for value in parsed.hook_variants if _safe_text(value, 64)]
        concepts = [_safe_text(value, 48) for value in parsed.broll_concepts if _safe_text(value, 48)]
        return CreativeFinishPlan(
            mood=mood,
            hook_variants=(hooks + fallback.hook_variants)[:3],
            broll_concepts=concepts[:6] or fallback.broll_concepts,
        )
    except Exception:
        return fallback


def _timeline_video_items(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    for track in timeline.get("tracks") or []:
        if track.get("type") == "video":
            return [item for item in track.get("items") or [] if item.get("enabled", True) is not False]
    return []


def _timeline_caption_items(timeline: dict[str, Any]) -> list[dict[str, Any]]:
    for track in timeline.get("tracks") or []:
        if track.get("type") == "captions":
            return list(track.get("items") or [])
    return []


def _dominant_face_center(source: Path, seconds: float) -> float | None:
    if cv2 is None:
        return None
    capture = cv2.VideoCapture(str(source))
    try:
        if not capture.isOpened():
            return None
        capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, seconds) * 1000.0)
        ok, frame = capture.read()
        if not ok or frame is None:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        cascade = cv2.CascadeClassifier(cascade_path)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.12, minNeighbors=5, minSize=(48, 48))
        if len(faces) == 0:
            return None
        x, _, w, _ = max(faces, key=lambda box: int(box[2]) * int(box[3]))
        width = float(frame.shape[1] or 1)
        return max(0.18, min(0.82, (float(x) + float(w) / 2.0) / width))
    except Exception:
        return None
    finally:
        capture.release()


def _auto_reframe_centers(source: Path, video_items: list[dict[str, Any]]) -> list[float]:
    centers: list[float] = []
    last = 0.5
    for item in video_items:
        start = float(item.get("source_in", 0.0))
        end = float(item.get("source_out", start))
        midpoint = start + max(0.0, end - start) / 2.0
        detected = _dominant_face_center(source, midpoint)
        if detected is not None:
            last = 0.68 * last + 0.32 * detected
        centers.append(round(last, 4))
    return centers


def _build_broll_items(timeline: dict[str, Any], concepts: list[str]) -> list[dict[str, Any]]:
    captions = _timeline_caption_items(timeline)
    duration = float(timeline.get("duration") or 0.0)
    if duration <= 0:
        return []
    items: list[dict[str, Any]] = []
    used: list[tuple[float, float]] = []
    for index, concept in enumerate(concepts[:4], start=1):
        tokens = [token.lower() for token in re.findall(r"[\wÀ-ÿ'-]+", concept) if len(token) >= 4]
        match = None
        for caption in captions:
            text = str(caption.get("text") or "").lower()
            if tokens and any(token in text for token in tokens):
                match = caption
                break
        if match is None and captions:
            match = captions[min(index * 2, len(captions) - 1)]
        if match is None:
            continue
        start = max(0.0, float(match.get("start", 0.0)))
        end = min(duration, max(start + 0.8, min(start + 1.9, float(match.get("end", start + 1.2)) + 0.8)))
        if any(not (end <= a or start >= b) for a, b in used):
            continue
        used.append((start, end))
        items.append(
            {
                "id": f"broll-{index}",
                "timeline_in": round(start, 3),
                "timeline_out": round(end, 3),
                "concept": concept,
                "source_type": "source_derived",
                "effect": "contextual_punch_in",
                "rights": "user_confirmed_source",
                "enabled": True,
            }
        )
    return items


def _clip_has_broll(item: dict[str, Any], broll_items: list[dict[str, Any]]) -> bool:
    start = float(item.get("timeline_in", 0.0))
    end = float(item.get("timeline_out", start))
    return any(
        cue.get("enabled", True) is not False
        and float(cue.get("timeline_out", 0.0)) > start
        and float(cue.get("timeline_in", 0.0)) < end
        for cue in broll_items
    )


def _escape_filter_path(path: Path) -> str:
    return path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")


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


def _render_reframed(
    source: Path,
    output: Path,
    video_items: list[dict[str, Any]],
    centers: list[float],
    ass_path: Path,
    broll_items: list[dict[str, Any]],
) -> None:
    if not video_items:
        raise RuntimeError("Timeline sem clipes para reenquadrar.")
    has_audio = _has_audio(source)
    chains: list[str] = []
    concat_inputs: list[str] = []
    total_duration = 0.0
    audio_label = "0:a" if has_audio else "1:a"

    for index, item in enumerate(video_items):
        start = float(item.get("source_in", 0.0))
        end = float(item.get("source_out", start))
        duration = max(0.08, end - start)
        total_duration += duration
        center = centers[index] if index < len(centers) else 0.5
        x_expr = f"max(0,min(in_w-1080,in_w*{center:.4f}-540))"
        extra = ",crop=972:1728:54:96,scale=1080:1920:flags=lanczos" if _clip_has_broll(item, broll_items) else ""
        chains.append(
            f"[0:v]trim=start={start:.3f}:duration={duration:.3f},setpts=PTS-STARTPTS,"
            f"scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop=1080:1920:x='{x_expr}':y='(in_h-1920)/2'{extra},"
            f"hqdn3d=1.2:1.2:6:6,eq=contrast=1.03:saturation=1.04[v{index}]"
        )
        audio_start = start if has_audio else 0.0
        chains.append(
            f"[{audio_label}]atrim=start={audio_start:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS,"
            f"highpass=f=80,alimiter=limit=0.95[a{index}]"
        )
        concat_inputs.append(f"[v{index}][a{index}]")

    chains.append("".join(concat_inputs) + f"concat=n={len(video_items)}:v=1:a=1[vcat][acat]")
    chains.append(f"[vcat]subtitles='{_escape_filter_path(ass_path)}'[vout]")
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


def _write_original_soundtrack(path: Path, duration: float, cut_times: list[float], mood: str) -> Path:
    sample_rate = 48000
    params = MOOD_AUDIO.get(mood, MOOD_AUDIO["energetic"])
    total_samples = max(1, int(duration * sample_rate))
    accents = [max(0, int(value * sample_rate)) for value in cut_times[:120]]
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        block = bytearray()
        for n in range(total_samples):
            t = n / sample_rate
            beat = 0.55 + 0.45 * max(0.0, math.sin(2.0 * math.pi * 2.0 * t))
            value = 0.015 * beat * math.sin(2.0 * math.pi * params["bed_hz"] * t)
            value += 0.007 * math.sin(2.0 * math.pi * params["pulse_hz"] * t)
            for accent in accents:
                delta = n - accent
                if 0 <= delta < int(0.11 * sample_rate):
                    env = 1.0 - delta / float(0.11 * sample_rate)
                    value += 0.045 * env * math.sin(2.0 * math.pi * params["accent_hz"] * (delta / sample_rate))
            pcm = max(-32767, min(32767, int(value * 32767)))
            block.extend(int(pcm).to_bytes(2, byteorder="little", signed=True))
            if len(block) >= 32768:
                handle.writeframesraw(bytes(block))
                block.clear()
        if block:
            handle.writeframesraw(bytes(block))
    return path


def _mix_sound_design(video: Path, soundtrack: Path, output: Path) -> None:
    _run(
        [
            settings.ffmpeg_binary,
            "-y",
            "-i",
            str(video),
            "-i",
            str(soundtrack),
            "-filter_complex",
            "[0:a]volume=1.0[a0];[1:a]volume=0.35[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2,loudnorm=I=-14:TP=-1.5:LRA=11[aout]",
            "-map",
            "0:v:0",
            "-map",
            "[aout]",
            "-c:v",
            "copy",
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


def _hook_ass(text: str, path: Path) -> Path:
    safe = text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", " ")
    content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Hook,Arial,84,&H00FFFFFF,&H0000FFB8,&H00101010,&H70000000,-1,0,0,0,100,100,0,0,1,6,1,8,85,85,250,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
Dialogue: 0,0:00:00.00,0:00:03.00,Hook,,0,0,0,,{{\\fad(80,120)\\fscx108\\fscy108\\t(0,180,\\fscx100\\fscy100)}}{safe}
"""
    path.write_text(content, encoding="utf-8")
    return path


def _render_hook_variant(preview: Path, output: Path, ass_path: Path, index: int) -> None:
    frequency = [620, 470, 760][index % 3]
    visual = (
        f"[0:v]subtitles='{_escape_filter_path(ass_path)}',"
        "scale=1080:1920:flags=lanczos[vout]"
    )
    _run(
        [
            settings.ffmpeg_binary,
            "-y",
            "-i",
            str(preview),
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration=0.18",
            "-filter_complex",
            visual + ";[1:a]volume=0.10,adelay=40|40[sfx];[0:a][sfx]amix=inputs=2:duration=first:dropout_transition=0.2[aout]",
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
            "-pix_fmt",
            "yuv420p",
            "-r",
            "30",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )


def _append_or_replace_track(timeline: dict[str, Any], track: dict[str, Any]) -> None:
    tracks = list(timeline.get("tracks") or [])
    tracks = [item for item in tracks if item.get("id") != track.get("id")]
    tracks.append(track)
    timeline["tracks"] = tracks


def enhance_editor_project(user_id: int, project_id: str) -> None:
    root = base.project_dir(user_id, project_id)
    project = base.read_project(user_id, project_id)
    timeline = dict(project.get("timeline") or {})
    source = root / str(project.get("source_filename") or "")
    ass_path = root / "captions.ass"
    if not source.is_file() or not ass_path.is_file() or not timeline:
        return

    base._set_project_state(user_id, project_id, status="rendering", progress=84)
    transcript = _load_transcript(root)
    creative = _creative_finish_plan(project, transcript, timeline)
    video_items = _timeline_video_items(timeline)
    broll_items = _build_broll_items(timeline, creative.broll_concepts)
    centers = _auto_reframe_centers(source, video_items)

    reframed = root / "preview-reframed.mp4"
    _render_reframed(source, reframed, video_items, centers, ass_path, broll_items)

    duration = float(timeline.get("duration") or 0.0)
    cut_times = [float(item.get("timeline_in", 0.0)) for item in video_items[1:]]
    soundtrack = _write_original_soundtrack(root / "sound-design.wav", duration, cut_times, creative.mood)
    final_preview = root / "preview.mp4"
    _mix_sound_design(reframed, soundtrack, final_preview)

    hooks: list[dict[str, Any]] = []
    for index, hook in enumerate(creative.hook_variants[:3]):
        label = chr(ord("A") + index)
        hook_ass = _hook_ass(hook, root / f"hook-{label.lower()}.ass")
        hook_output = root / f"hook-variant-{label.lower()}.mp4"
        _render_hook_variant(final_preview, hook_output, hook_ass, index)
        hooks.append(
            {
                "variant": label,
                "text": hook,
                "duration_seconds": 3,
                "media_url": f"/api/media/editor-projects/{project_id}/{hook_output.name}",
            }
        )

    _append_or_replace_track(
        timeline,
        {
            "id": "broll-contextual",
            "type": "broll",
            "locked": False,
            "items": broll_items,
        },
    )
    _append_or_replace_track(
        timeline,
        {
            "id": "sound-design",
            "type": "audio_fx",
            "locked": False,
            "items": [
                {
                    "id": "generated-bed",
                    "source": "sound-design.wav",
                    "timeline_in": 0,
                    "timeline_out": round(duration, 3),
                    "mood": creative.mood,
                    "rights": "procedurally_generated_original",
                    "enabled": True,
                }
            ],
        },
    )
    _append_or_replace_track(
        timeline,
        {
            "id": "hook-variants",
            "type": "variations",
            "locked": False,
            "items": hooks,
        },
    )
    (root / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    analysis = dict(project.get("analysis") or {})
    analysis["auto_reframe"] = {
        "enabled": True,
        "mode": "shot_face_tracking" if cv2 is not None else "safe_center_fallback",
        "tracked_shots": sum(1 for center in centers if abs(center - 0.5) > 0.015),
        "total_shots": len(centers),
        "aspect_ratio": "9:16",
    }
    analysis["sound_design"] = {
        "enabled": True,
        "mood": creative.mood,
        "music_source": "procedurally_generated_original",
        "cut_sync_points": len(cut_times),
        "voice_target_lufs": -14,
    }
    analysis["broll"] = {
        "enabled": True,
        "strategy": "contextual_source_derived",
        "items": len(broll_items),
        "concepts": creative.broll_concepts,
        "rights": "user_confirmed_source_only",
    }
    analysis["hook_variations"] = hooks
    analysis["social_formats"] = {
        "tiktok_shop": "1080x1920 9:16",
        "instagram_reels": "1080x1920 9:16",
        "youtube_shorts": "1080x1920 9:16",
    }

    base._set_project_state(
        user_id,
        project_id,
        status="ready",
        progress=100,
        timeline=timeline,
        analysis=analysis,
        preview_url=f"/api/media/editor-projects/{project_id}/preview.mp4",
        hook_variants=hooks,
    )


def run_claimed_editor_task(user_id: int, project_id: str, mode: str) -> None:
    if mode == "export":
        base.export_editor_project(user_id, project_id)
        return
    base.process_editor_project(user_id, project_id)
    project = base.read_project(user_id, project_id)
    if project.get("status") == "ready":
        try:
            enhance_editor_project(user_id, project_id)
        except Exception as exc:
            # Preserve the already-rendered base edit as usable fallback and expose the finishing failure.
            current = base.read_project(user_id, project_id)
            analysis = dict(current.get("analysis") or {})
            notes = list(analysis.get("notes") or [])
            notes.append(f"Acabamento avançado indisponível; preview base preservado: {exc}")
            analysis["notes"] = notes
            base._set_project_state(
                user_id,
                project_id,
                status="ready",
                progress=100,
                analysis=analysis,
                preview_url=f"/api/media/editor-projects/{project_id}/preview.mp4",
            )
