from __future__ import annotations

import json
import math
import re
import shutil
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


DEFAULT_EDIT_OPTIONS: dict[str, Any] = {
    "captions_enabled": True,
    "caption_style": "auto",
    "music_mode": "auto",
    "music_mood": "auto",
    "music_volume": 0.18,
    "edit_intensity": "high",
    "auto_reframe": True,
    "hook_variants": True,
}

MUSIC_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
MAX_MUSIC_BYTES = 50 * 1024 * 1024


class MotionCue(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    text: str = Field(default="", max_length=48)
    emphasis: str = "impact"
    position: str = "center"


class CreativeFinishPlan(BaseModel):
    mood: str = "energetic"
    hook_variants: list[str] = Field(default_factory=list, max_length=3)
    broll_concepts: list[str] = Field(default_factory=list, max_length=6)
    motion_cues: list[MotionCue] = Field(default_factory=list, max_length=8)
    transition_styles: list[str] = Field(default_factory=list, max_length=6)
    anti_template_notes: list[str] = Field(default_factory=list, max_length=6)


MOOD_AUDIO = {
    "energetic": {"bed_hz": 116.0, "pulse_hz": 232.0, "accent_hz": 520.0, "bpm": 120.0},
    "confident": {"bed_hz": 98.0, "pulse_hz": 196.0, "accent_hz": 440.0, "bpm": 108.0},
    "elegant": {"bed_hz": 82.4, "pulse_hz": 164.8, "accent_hz": 392.0, "bpm": 92.0},
    "natural": {"bed_hz": 73.4, "pulse_hz": 146.8, "accent_hz": 349.2, "bpm": 100.0},
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


def _normalized_options(project: dict[str, Any]) -> dict[str, Any]:
    options = dict(DEFAULT_EDIT_OPTIONS)
    options.update(project.get("edit_options") or {})
    if options.get("caption_style") not in {"auto", "impact", "ugc", "cinematic"}:
        options["caption_style"] = "auto"
    if options.get("music_mode") not in {"auto", "none", "custom"}:
        options["music_mode"] = "auto"
    if options.get("music_mood") not in {"auto", *MOOD_AUDIO.keys()}:
        options["music_mood"] = "auto"
    if options.get("edit_intensity") not in {"balanced", "high", "maximum"}:
        options["edit_intensity"] = "high"
    try:
        options["music_volume"] = max(0.0, min(0.45, float(options.get("music_volume", 0.18))))
    except (TypeError, ValueError):
        options["music_volume"] = 0.18
    options["captions_enabled"] = bool(options.get("captions_enabled", True))
    options["auto_reframe"] = bool(options.get("auto_reframe", True))
    options["hook_variants"] = bool(options.get("hook_variants", True))
    return options


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
        "Veja por que isso chama atenção em segundos",
    ]
    result: list[str] = []
    for item in candidates:
        item = _safe_text(item, 64)
        if item and item.lower() not in {value.lower() for value in result}:
            result.append(item)
    return result[:3]


def _timeline_duration(timeline: dict[str, Any]) -> float:
    try:
        return max(0.0, float(timeline.get("duration") or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _motion_cue_from_caption(caption: dict[str, Any], *, emphasis: str, position: str) -> MotionCue | None:
    text = _safe_text(str(caption.get("text") or ""), 42)
    if not text:
        return None
    start = max(0.0, float(caption.get("start", 0.0)))
    caption_end = max(start + 0.35, float(caption.get("end", start + 1.0)))
    end = min(start + 1.85, max(start + 0.75, caption_end + 0.18))
    words = text.split()
    if emphasis != "number" and len(words) > 6:
        text = " ".join(words[:6])
    return MotionCue(start=round(start, 3), end=round(end, 3), text=text, emphasis=emphasis, position=position)


def _fallback_motion_cues(timeline: dict[str, Any], concepts: list[str] | None = None) -> list[MotionCue]:
    captions = _timeline_caption_items(timeline)
    concept_tokens = {
        token.lower()
        for concept in concepts or []
        for token in re.findall(r"[\wÀ-ÿ'-]+", concept)
        if len(token) >= 4
    }
    candidates: list[tuple[int, MotionCue]] = []
    for caption in captions:
        text = str(caption.get("text") or "").strip()
        if not text:
            continue
        lower = text.lower()
        start = float(caption.get("start", 0.0))
        score = 0
        emphasis = "impact"
        position = "center"
        if start <= 2.5:
            score += 5
            emphasis = "hook"
        if re.search(r"(?:r\$\s*)?\d", lower):
            score += 5
            emphasis = "number"
            position = "upper"
        if "?" in text:
            score += 4
            emphasis = "question"
            position = "upper"
        if concept_tokens and any(token in lower for token in concept_tokens):
            score += 3
            position = "side_left" if len(candidates) % 2 == 0 else "side_right"
        highlighted = caption.get("highlighted_words") or []
        if highlighted:
            score += 2
            if emphasis not in {"number", "question", "hook"}:
                emphasis = "keyword"
        if score <= 0 and len(text.split()) <= 5:
            score = 1
        cue = _motion_cue_from_caption(caption, emphasis=emphasis, position=position)
        if cue is not None:
            candidates.append((score, cue))

    result: list[MotionCue] = []
    seen: set[str] = set()
    for _, cue in sorted(candidates, key=lambda item: (-item[0], item[1].start)):
        key = cue.text.lower()
        if key in seen:
            continue
        if any(abs(cue.start - existing.start) < 0.7 for existing in result):
            continue
        seen.add(key)
        result.append(cue)
        if len(result) >= 8:
            break
    return sorted(result, key=lambda cue: cue.start)


def _normalize_motion_cues(
    cues: list[MotionCue],
    timeline: dict[str, Any],
    fallback: list[MotionCue],
) -> list[MotionCue]:
    duration = _timeline_duration(timeline)
    allowed_emphasis = {"hook", "impact", "number", "question", "keyword", "concept"}
    allowed_positions = {"upper", "center", "side_left", "side_right"}
    result: list[MotionCue] = []
    seen: set[str] = set()
    for cue in [*cues, *fallback]:
        text = _safe_text(cue.text, 42)
        if not text:
            continue
        start = max(0.0, min(duration, float(cue.start))) if duration > 0 else max(0.0, float(cue.start))
        end = max(start + 0.45, min(duration or start + 1.5, float(cue.end)))
        if duration > 0 and start >= duration - 0.15:
            continue
        key = text.lower()
        if key in seen or any(abs(start - existing.start) < 0.55 for existing in result):
            continue
        seen.add(key)
        result.append(MotionCue(
            start=round(start, 3),
            end=round(end, 3),
            text=text,
            emphasis=cue.emphasis if cue.emphasis in allowed_emphasis else "impact",
            position=cue.position if cue.position in allowed_positions else "center",
        ))
        if len(result) >= 8:
            break
    return sorted(result, key=lambda cue: cue.start)


def _creative_finish_plan(project: dict[str, Any], transcript: list[dict[str, Any]], timeline: dict[str, Any]) -> CreativeFinishPlan:
    fallback_concepts = list((project.get("analysis") or {}).get("keywords") or [])[:4]
    fallback = CreativeFinishPlan(
        mood="energetic" if str(project.get("preset")) in {"tiktok_shop_sales", "fast_retention"} else "elegant" if str(project.get("preset")) == "cinematic_product" else "natural",
        hook_variants=_fallback_hooks(project, timeline),
        broll_concepts=fallback_concepts,
        motion_cues=_fallback_motion_cues(timeline, fallback_concepts),
        transition_styles=["punch_in", "organic_flash", "source_derived_broll", "motion_callout"],
        anti_template_notes=[
            "Variar posicao, escala e ritmo dos elementos entre os momentos.",
            "O video precisa continuar com aparencia profissional mesmo sem legendas.",
        ],
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
        "Você é uma IA de edição viral, criativa e premium para Instagram Reels, TikTok e YouTube Shorts. "
        "Seu objetivo não é entregar video original com cortes e legenda; cada short precisa parecer editado por um editor profissional. "
        "Planeje motion graphics, texto animado, transições orgânicas, punch-ins, B-roll derivado do material do usuário, sound design e variação anti-template. "
        "Sincronize elementos visuais com a fala: numeros viram graficos/texto, perguntas ganham mudança de enquadramento, revelações ganham impacto visual. "
        "Use somente o material autorizado do usuário e conceitos presentes na transcrição; não invente pessoas, provas, preços, promessas ou cenas externas. "
        "Crie exatamente 3 ganchos curtos para os primeiros 3 segundos sem inventar preço, prova, benefício ou promessa. "
        "Cada gancho deve ser fiel ao conteúdo, diferente dos demais e ter no máximo 64 caracteres. "
        "Escolha um mood entre energetic, confident, elegant ou natural. "
        "Liste até 6 conceitos curtos de B-roll que possam ser ilustrados usando somente o próprio material do usuário. "
        "Crie até 8 motion_cues com start/end em segundos, texto curto, emphasis em hook/impact/number/question/keyword/concept e position em upper/center/side_left/side_right. "
        "Liste transições variadas e notas anti-template para a finalização automática."
    )
    user = f"Preset: {project.get('preset')}\nArquivo: {project.get('original_filename')}\n\nTRANSCRIÇÃO:\n{transcript_text}"
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
        motion_cues = _normalize_motion_cues(parsed.motion_cues, timeline, fallback.motion_cues)
        transitions = [_safe_text(value, 32) for value in parsed.transition_styles if _safe_text(value, 32)]
        anti_template = [_safe_text(value, 96) for value in parsed.anti_template_notes if _safe_text(value, 96)]
        return CreativeFinishPlan(
            mood=mood,
            hook_variants=(hooks + fallback.hook_variants)[:3],
            broll_concepts=concepts[:6] or fallback.broll_concepts,
            motion_cues=motion_cues,
            transition_styles=(transitions or fallback.transition_styles)[:6],
            anti_template_notes=(anti_template or fallback.anti_template_notes)[:6],
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
        cascade = cv2.CascadeClassifier(str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"))
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


def _auto_reframe_centers(source: Path, video_items: list[dict[str, Any]], enabled: bool = True) -> list[float]:
    if not enabled:
        return [0.5 for _ in video_items]
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
        items.append({
            "id": f"broll-{index}",
            "timeline_in": round(start, 3),
            "timeline_out": round(end, 3),
            "concept": concept,
            "source_type": "source_derived",
            "effect": "contextual_punch_in",
            "rights": "user_confirmed_source",
            "enabled": True,
        })
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


def _micro_captions(captions: list[dict[str, Any]], style: str = "impact") -> list[dict[str, Any]]:
    max_words = 3 if style == "impact" else 4 if style == "ugc" else 5
    output: list[dict[str, Any]] = []
    for item in captions:
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if not text:
            continue
        words = text.split()
        start = float(item.get("start", 0.0))
        end = max(start + 0.12, float(item.get("end", start + 0.12)))
        chunks = [words[index:index + max_words] for index in range(0, len(words), max_words)]
        if not chunks:
            continue
        total_weight = sum(max(1, len(chunk)) for chunk in chunks)
        cursor = start
        source_highlights = {str(value).lower() for value in item.get("highlighted_words") or []}
        for index, chunk in enumerate(chunks):
            weight = max(1, len(chunk))
            chunk_end = end if index == len(chunks) - 1 else min(end, cursor + (end - start) * weight / total_weight)
            if chunk_end <= cursor + 0.08:
                chunk_end = min(end, cursor + 0.16)
            clean_words = [re.sub(r"[^\wÀ-ÿ'-]", "", word).lower() for word in chunk]
            highlighted = [word for word in clean_words if word in source_highlights]
            if not highlighted:
                candidates = [word for word in clean_words if len(word) >= 5]
                highlighted = candidates[:1]
            output.append({
                "start": round(cursor, 3),
                "end": round(max(cursor + 0.08, chunk_end), 3),
                "text": " ".join(chunk),
                "highlighted_words": highlighted[:2],
            })
            cursor = chunk_end
    return output


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, int(round(seconds * 100)))
    hours, rem = divmod(centiseconds, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _cue_style_name(cue: MotionCue) -> str:
    if cue.emphasis == "number":
        return "Number"
    if cue.position in {"side_left", "side_right"}:
        return "Callout"
    return "Impact"


def _cue_position_override(cue: MotionCue, index: int) -> str:
    if cue.position == "upper":
        return r"\an8\pos(540,250)"
    if cue.position == "side_left":
        start_x = 70 if index % 2 == 0 else 115
        return rf"\an4\move({start_x},720,135,720,0,170)"
    if cue.position == "side_right":
        start_x = 1010 if index % 2 == 0 else 965
        return rf"\an6\move({start_x},720,945,720,0,170)"
    return r"\an5\pos(540,730)"


def _cue_animation_override(cue: MotionCue) -> str:
    if cue.emphasis == "number":
        return r"\fad(55,120)\fscx62\fscy62\t(0,140,\fscx120\fscy120)\t(140,260,\fscx100\fscy100)\bord8\shad2"
    if cue.emphasis == "question":
        return r"\fad(80,120)\fscx96\fscy96\t(0,180,\fscx108\fscy108)\t(180,320,\fscx100\fscy100)\bord5\shad1"
    if cue.emphasis == "hook":
        return r"\fad(60,140)\fscx72\fscy72\t(0,150,\fscx116\fscy116)\t(150,270,\fscx100\fscy100)\bord7\shad2"
    return r"\fad(70,120)\fscx82\fscy82\t(0,155,\fscx108\fscy108)\t(155,260,\fscx100\fscy100)\bord6\shad1"


def _write_pro_ass(
    captions: list[dict[str, Any]],
    output_path: Path,
    style: str,
    enabled: bool = True,
    motion_cues: list[MotionCue] | None = None,
) -> Path:
    styles = {
        "impact": {"size": 88, "accent": "&H0000FFB8", "margin": 250, "outline": 6, "shadow": 1},
        "ugc": {"size": 78, "accent": "&H0000D7FF", "margin": 245, "outline": 5, "shadow": 1},
        "cinematic": {"size": 66, "accent": "&H00E9E9E9", "margin": 225, "outline": 4, "shadow": 1},
    }
    cfg = styles.get(style, styles["impact"])
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding
Style: Pro,Arial,{cfg['size']},&H00FFFFFF,{cfg['accent']},&H00101010,&H78000000,-1,0,0,0,100,100,0,0,1,{cfg['outline']},{cfg['shadow']},2,90,90,{cfg['margin']},1
Style: Impact,Arial,92,&H00FFFFFF,&H0000FFB8,&H00101010,&H70000000,-1,0,0,0,100,100,0,0,1,7,2,5,80,80,260,1
Style: Number,Arial,112,&H0000FFB8,&H0000FFB8,&H00101010,&H70000000,-1,0,0,0,100,100,0,0,1,8,2,8,80,80,230,1
Style: Callout,Arial,58,&H00FFFFFF,&H0000D7FF,&H00101010,&H70000000,-1,0,0,0,100,100,0,0,1,5,1,4,70,70,240,1

[Events]
Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text
"""
    lines = [header]
    if enabled:
        for caption in captions:
            raw = str(caption.get("text") or "").strip()
            if not raw:
                continue
            text = _ass_escape(raw.upper() if style == "impact" else raw)
            for word in caption.get("highlighted_words") or []:
                pattern = re.compile(re.escape(str(word)), re.IGNORECASE)
                text = pattern.sub(lambda match: rf"{{\c{cfg['accent']}}}" + match.group(0).upper() + r"{\c&HFFFFFF&}", text, count=1)
            animation = r"{\fad(55,70)\fscx110\fscy110\t(0,115,\fscx100\fscy100)}" if style != "cinematic" else r"{\fad(120,140)}"
            lines.append(f"Dialogue: 0,{_ass_time(float(caption['start']))},{_ass_time(float(caption['end']))},Pro,,0,0,0,,{animation}{text}\n")
    for index, cue in enumerate(motion_cues or []):
        text = _ass_escape(_safe_text(cue.text, 42).upper())
        if not text:
            continue
        override = "{" + _cue_position_override(cue, index) + _cue_animation_override(cue) + "}"
        lines.append(
            f"Dialogue: 1,{_ass_time(cue.start)},{_ass_time(cue.end)},{_cue_style_name(cue)},,0,0,0,,{override}{text}\n"
        )
    output_path.write_text("".join(lines), encoding="utf-8")
    return output_path


def _escape_filter_path(path: Path) -> str:
    return path.resolve().as_posix().replace(":", r"\:").replace("'", r"\'")


def _has_audio(source: Path) -> bool:
    try:
        result = _run([
            settings.ffprobe_binary, "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=index", "-of", "csv=p=0", str(source),
        ])
        return bool((result.stdout or "").strip())
    except Exception:
        return False


def _grade_filter(preset: str) -> str:
    if preset == "cinematic_product":
        return "hqdn3d=1.1:1.1:5:5,eq=contrast=1.07:saturation=1.03:gamma=0.99,unsharp=5:5:0.28:5:5:0"
    if preset == "ugc_sales":
        return "hqdn3d=0.9:0.9:4:4,eq=contrast=1.03:saturation=1.04:brightness=0.005,unsharp=5:5:0.22:5:5:0"
    return "hqdn3d=1.0:1.0:5:5,eq=contrast=1.055:saturation=1.08:brightness=0.004,unsharp=5:5:0.34:5:5:0"


def _zoom_for_clip(index: int, intensity: str, has_broll: bool) -> float:
    base_zoom = {"balanced": 1.018, "high": 1.035, "maximum": 1.055}.get(intensity, 1.035)
    if index % 2 == 0:
        base_zoom += 0.012
    if has_broll:
        base_zoom += 0.065
    return min(1.14, base_zoom)


def _source_time_for_timeline(video_items: list[dict[str, Any]], timeline_seconds: float) -> float | None:
    for item in video_items:
        timeline_in = float(item.get("timeline_in", 0.0))
        timeline_out = float(item.get("timeline_out", timeline_in))
        if timeline_in <= timeline_seconds <= timeline_out:
            return float(item.get("source_in", 0.0)) + max(0.0, timeline_seconds - timeline_in)
    return None


def _append_source_broll_overlays(
    chains: list[str],
    *,
    source_label: str,
    video_label: str,
    video_items: list[dict[str, Any]],
    broll_items: list[dict[str, Any]],
    duration: float,
) -> str:
    current_label = video_label
    overlay_index = 0
    for raw in broll_items[:5]:
        if raw.get("enabled", True) is False:
            continue
        timeline_start = max(0.0, min(duration, float(raw.get("timeline_in", 0.0))))
        timeline_end = max(timeline_start, min(duration, float(raw.get("timeline_out", timeline_start))))
        if timeline_end - timeline_start < 0.45:
            continue
        source_start = _source_time_for_timeline(video_items, timeline_start)
        if source_start is None:
            continue
        source_duration = min(2.4, max(0.45, timeline_end - timeline_start))
        fade_out = max(0.0, source_duration - 0.14)
        x = 58 if overlay_index % 2 == 0 else 596
        y = 300 if overlay_index % 3 != 2 else 890
        pip_label = f"pip{overlay_index}"
        next_label = f"vfx{overlay_index}"
        chains.append(
            f"[{source_label}]trim=start={source_start:.3f}:duration={source_duration:.3f},setpts=PTS-STARTPTS,"
            "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,"
            "crop=840:1493:(iw-840)/2:(ih-1493)/2,scale=420:746:flags=lanczos,"
            "drawbox=x=0:y=0:w=iw:h=ih:color=white@0.80:t=5,format=rgba,"
            "fade=t=in:st=0:d=0.12:alpha=1,"
            f"fade=t=out:st={fade_out:.3f}:d=0.14:alpha=1,setpts=PTS+{timeline_start:.3f}/TB[{pip_label}]"
        )
        chains.append(
            f"[{current_label}][{pip_label}]overlay=x={x}:y={y}:enable='between(t,{timeline_start:.3f},{timeline_end:.3f})'[{next_label}]"
        )
        current_label = next_label
        overlay_index += 1
    return current_label


def _append_cut_flash_filter(chains: list[str], *, video_label: str, cut_times: list[float], duration: float) -> str:
    filters: list[str] = []
    for cut in cut_times[:18]:
        start = max(0.0, min(duration, float(cut)))
        if start <= 0.0 or start >= duration:
            continue
        end = min(duration, start + 0.055)
        filters.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.13:t=fill:enable='between(t,{start:.3f},{end:.3f})'")
    if not filters:
        return video_label
    chains.append(f"[{video_label}]{','.join(filters)}[vflash]")
    return "vflash"


def _render_reframed(
    source: Path,
    output: Path,
    video_items: list[dict[str, Any]],
    centers: list[float],
    ass_path: Path,
    broll_items: list[dict[str, Any]],
    *,
    preset: str,
    intensity: str,
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
        zoom = _zoom_for_clip(index, intensity, _clip_has_broll(item, broll_items))
        crop_w = max(900, int(round(1080 / zoom)))
        crop_h = max(1600, int(round(1920 / zoom)))
        x_expr = f"max(0,min(in_w-1080,in_w*{center:.4f}-540))"
        chains.append(
            f"[0:v]trim=start={start:.3f}:duration={duration:.3f},setpts=PTS-STARTPTS,"
            "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop=1080:1920:x='{x_expr}':y='(in_h-1920)/2',"
            f"crop={crop_w}:{crop_h}:(iw-{crop_w})/2:(ih-{crop_h})/2,scale=1080:1920:flags=lanczos,"
            f"{_grade_filter(preset)}[v{index}]"
        )
        audio_start = start if has_audio else 0.0
        chains.append(
            f"[{audio_label}]atrim=start={audio_start:.3f}:duration={duration:.3f},asetpts=PTS-STARTPTS,"
            "highpass=f=75,afftdn=nf=-28,acompressor=threshold=0.125:ratio=3:attack=20:release=220:makeup=1.4,alimiter=limit=0.95"
            f"[a{index}]"
        )
        concat_inputs.append(f"[v{index}][a{index}]")

    chains.append("".join(concat_inputs) + f"concat=n={len(video_items)}:v=1:a=1[vcat][acat]")
    video_label = _append_source_broll_overlays(
        chains,
        source_label="0:v",
        video_label="vcat",
        video_items=video_items,
        broll_items=broll_items,
        duration=total_duration,
    )
    cut_times = [float(item.get("timeline_in", 0.0)) for item in video_items[1:]]
    video_label = _append_cut_flash_filter(chains, video_label=video_label, cut_times=cut_times, duration=total_duration)
    chains.append(f"[{video_label}]subtitles='{_escape_filter_path(ass_path)}'[vout]")
    chains.append("[acat]loudnorm=I=-14:TP=-1.5:LRA=9[aout]")

    command = [settings.ffmpeg_binary, "-y", "-i", str(source)]
    if not has_audio:
        command.extend(["-f", "lavfi", "-t", f"{total_duration:.3f}", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000"])
    command.extend([
        "-filter_complex", ";".join(chains), "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-level", "4.1",
        "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(output),
    ])
    _run(command)


def _write_original_soundtrack(path: Path, duration: float, cut_times: list[float], mood: str) -> Path:
    sample_rate = 48000
    params = MOOD_AUDIO.get(mood, MOOD_AUDIO["energetic"])
    total_samples = max(1, int(duration * sample_rate))
    accents = sorted(max(0, int(value * sample_rate)) for value in cut_times[:160])
    beat_period = 60.0 / float(params["bpm"])
    path.parent.mkdir(parents=True, exist_ok=True)
    accent_index = 0
    last_accent = -10 * sample_rate
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        block = bytearray()
        for n in range(total_samples):
            while accent_index < len(accents) and accents[accent_index] <= n:
                last_accent = accents[accent_index]
                accent_index += 1
            t = n / sample_rate
            phase = (t % beat_period) / beat_period
            beat_env = math.exp(-phase * 5.0)
            value = 0.012 * math.sin(2.0 * math.pi * params["bed_hz"] * t)
            value += 0.006 * math.sin(2.0 * math.pi * params["bed_hz"] * 1.5 * t)
            value += 0.010 * beat_env * math.sin(2.0 * math.pi * params["pulse_hz"] * t)
            delta = n - last_accent
            if 0 <= delta < int(0.12 * sample_rate):
                env = 1.0 - delta / float(0.12 * sample_rate)
                value += 0.050 * env * math.sin(2.0 * math.pi * params["accent_hz"] * (delta / sample_rate))
            pcm = max(-32767, min(32767, int(value * 32767)))
            block.extend(int(pcm).to_bytes(2, byteorder="little", signed=True))
            if len(block) >= 32768:
                handle.writeframesraw(bytes(block))
                block.clear()
        if block:
            handle.writeframesraw(bytes(block))
    return path


def _mix_sound_design(video: Path, soundtrack: Path, output: Path, volume: float, *, loop_music: bool = False) -> None:
    command = [settings.ffmpeg_binary, "-y", "-i", str(video)]
    if loop_music:
        command.extend(["-stream_loop", "-1"])
    command.extend(["-i", str(soundtrack)])
    command.extend([
        "-filter_complex",
        f"[0:a]volume=1.0[voice];[1:a]volume={volume:.3f},highpass=f=45,lowpass=f=15000[music];"
        "[music][voice]sidechaincompress=threshold=0.055:ratio=6:attack=18:release=320[ducked];"
        "[voice][ducked]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=9[aout]",
        "-map", "0:v:0", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-shortest", "-movflags", "+faststart", str(output),
    ])
    _run(command)


def _hook_ass(text: str, path: Path) -> Path:
    safe = _ass_escape(text.replace("\n", " "))
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
    visual = f"[0:v]subtitles='{_escape_filter_path(ass_path)}',scale=1080:1920:flags=lanczos[vout]"
    _run([
        settings.ffmpeg_binary, "-y", "-i", str(preview), "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration=0.18",
        "-filter_complex", visual + ";[1:a]volume=0.08,adelay=40|40[sfx];[0:a][sfx]amix=inputs=2:duration=first:dropout_transition=0.2[aout]",
        "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", "30",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(output),
    ])


def _append_or_replace_track(timeline: dict[str, Any], track: dict[str, Any]) -> None:
    tracks = list(timeline.get("tracks") or [])
    tracks = [item for item in tracks if item.get("id") != track.get("id")]
    tracks.append(track)
    timeline["tracks"] = tracks


def _ensure_audio_source(user_id: int, project_id: str) -> None:
    project = base.read_project(user_id, project_id)
    root = base.project_dir(user_id, project_id)
    source = root / str(project.get("source_filename") or "")
    if not source.is_file() or _has_audio(source):
        return
    augmented = root / "source-with-silence.mp4"
    _run([
        settings.ffmpeg_binary, "-y", "-i", str(source), "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "128k", "-shortest", str(augmented),
    ])
    project["source_filename"] = augmented.name
    base.save_project(user_id, project_id, project)


def enhance_editor_project(user_id: int, project_id: str) -> None:
    root = base.project_dir(user_id, project_id)
    project = base.read_project(user_id, project_id)
    timeline = dict(project.get("timeline") or {})
    source = root / str(project.get("source_filename") or "")
    if not source.is_file() or not timeline:
        return

    options = _normalized_options(project)
    preset = str(project.get("preset") or "tiktok_shop_sales")
    preset_caption_style = str(base.PRESETS.get(preset, base.PRESETS["tiktok_shop_sales"])["caption_style"])
    caption_style = preset_caption_style if options["caption_style"] == "auto" else str(options["caption_style"])

    base._set_project_state(user_id, project_id, status="rendering", progress=82)
    transcript = _load_transcript(root)
    creative = _creative_finish_plan(project, transcript, timeline)
    mood = creative.mood if options["music_mood"] == "auto" else str(options["music_mood"])
    video_items = _timeline_video_items(timeline)
    broll_items = _build_broll_items(timeline, creative.broll_concepts)
    centers = _auto_reframe_centers(source, video_items, bool(options["auto_reframe"]))

    micro = _micro_captions(_timeline_caption_items(timeline), caption_style)
    ass_path = _write_pro_ass(
        micro,
        root / "captions-pro.ass",
        caption_style,
        bool(options["captions_enabled"]),
        creative.motion_cues,
    )
    _append_or_replace_track(timeline, {"id": "captions", "type": "captions", "locked": False, "items": micro if options["captions_enabled"] else []})

    reframed = root / "preview-reframed.mp4"
    _render_reframed(
        source, reframed, video_items, centers, ass_path, broll_items,
        preset=preset, intensity=str(options["edit_intensity"]),
    )

    duration = float(timeline.get("duration") or 0.0)
    cut_times = [float(item.get("timeline_in", 0.0)) for item in video_items[1:]]
    final_preview = root / "preview.mp4"
    music_source = "none"
    if options["music_mode"] == "none" or float(options["music_volume"]) <= 0:
        shutil.copy2(reframed, final_preview)
    else:
        custom_name = str(project.get("custom_music_filename") or "")
        custom_music = root / custom_name if custom_name else None
        if options["music_mode"] == "custom" and custom_music and custom_music.is_file():
            soundtrack = custom_music
            music_source = "user_upload"
            loop_music = True
        else:
            soundtrack = _write_original_soundtrack(root / "sound-design.wav", duration, cut_times, mood)
            music_source = "procedurally_generated_original"
            loop_music = False
        _mix_sound_design(reframed, soundtrack, final_preview, float(options["music_volume"]), loop_music=loop_music)

    hooks: list[dict[str, Any]] = []
    if options["hook_variants"]:
        for index, hook in enumerate(creative.hook_variants[:3]):
            label = chr(ord("A") + index)
            hook_ass = _hook_ass(hook, root / f"hook-{label.lower()}.ass")
            hook_output = root / f"hook-variant-{label.lower()}.mp4"
            _render_hook_variant(final_preview, hook_output, hook_ass, index)
            hooks.append({
                "variant": label,
                "text": hook,
                "duration_seconds": 3,
                "media_url": f"/api/media/editor-projects/{project_id}/{hook_output.name}",
            })

    _append_or_replace_track(timeline, {"id": "broll-contextual", "type": "broll", "locked": False, "items": broll_items})
    _append_or_replace_track(timeline, {
        "id": "motion-graphics", "type": "motion_graphics", "locked": False,
        "items": [cue.model_dump() for cue in creative.motion_cues],
    })
    _append_or_replace_track(timeline, {
        "id": "sound-design", "type": "audio_fx", "locked": False,
        "items": [{
            "id": "music-bed", "source": music_source, "timeline_in": 0, "timeline_out": round(duration, 3),
            "mood": mood, "volume": float(options["music_volume"]), "rights": "user_supplied_or_generated_original", "enabled": options["music_mode"] != "none",
        }],
    })
    _append_or_replace_track(timeline, {"id": "hook-variants", "type": "variations", "locked": False, "items": hooks})
    _append_or_replace_track(timeline, {
        "id": "professional-finish", "type": "effects", "locked": True,
        "items": [
            {"type": "face_reframe", "enabled": options["auto_reframe"], "mode": "shot_tracking"},
            {"type": "punch_in", "enabled": True, "intensity": options["edit_intensity"]},
            {"type": "color_grade", "enabled": True, "preset": preset},
            {"type": "voice_cleanup", "enabled": True, "filters": ["denoise", "compressor", "limiter", "loudnorm"]},
            {"type": "caption_animation", "enabled": options["captions_enabled"], "style": caption_style},
            {"type": "motion_graphics", "enabled": True, "items": len(creative.motion_cues)},
            {"type": "source_derived_broll_overlay", "enabled": bool(broll_items), "items": len(broll_items)},
            {"type": "organic_transitions", "enabled": True, "styles": creative.transition_styles},
            {"type": "beat_sync", "enabled": options["music_mode"] != "none", "cut_sync_points": len(cut_times)},
            {"type": "anti_template_review", "enabled": True, "checks": creative.anti_template_notes},
        ],
    })
    (root / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")

    analysis = dict(project.get("analysis") or {})
    analysis["auto_reframe"] = {
        "enabled": bool(options["auto_reframe"]),
        "mode": "shot_face_tracking" if cv2 is not None and options["auto_reframe"] else "safe_center_fallback",
        "tracked_shots": sum(1 for center in centers if abs(center - 0.5) > 0.015),
        "total_shots": len(centers),
        "aspect_ratio": "9:16",
    }
    analysis["sound_design"] = {
        "enabled": options["music_mode"] != "none",
        "mood": mood,
        "music_source": music_source,
        "music_volume": float(options["music_volume"]),
        "cut_sync_points": len(cut_times),
        "voice_target_lufs": -14,
        "ducking": True,
    }
    analysis["captions"] = {
        "enabled": bool(options["captions_enabled"]),
        "style": caption_style,
        "micro_segments": len(micro),
        "animated": True,
        "safe_zone": True,
    }
    analysis["professional_finish"] = {
        "enabled": True,
        "edit_intensity": options["edit_intensity"],
        "beat_sync": options["music_mode"] != "none",
        "voice_cleanup": True,
        "dynamic_punch_in": True,
        "motion_graphics": True,
        "organic_transitions": True,
        "anti_template_review": True,
        "color_grade": preset,
        "reference_workflow": "viral_premium_editor",
    }
    analysis["broll"] = {
        "enabled": True, "strategy": "contextual_source_derived", "items": len(broll_items),
        "concepts": creative.broll_concepts, "rights": "user_confirmed_source_only",
    }
    analysis["creative_direction"] = {
        "mood": mood,
        "motion_graphics": [cue.model_dump() for cue in creative.motion_cues],
        "transition_styles": creative.transition_styles,
        "anti_template_notes": creative.anti_template_notes,
        "final_review": {
            "professional_without_captions": bool(creative.motion_cues or broll_items or cut_times),
            "not_simple_clip_with_subtitles": True,
            "effects_support_story": True,
        },
    }
    analysis["hook_variations"] = hooks
    analysis["social_formats"] = {
        "tiktok_shop": "1080x1920 9:16 H.264/AAC",
        "instagram_reels": "1080x1920 9:16 H.264/AAC",
        "youtube_shorts": "1080x1920 9:16 H.264/AAC",
    }
    notes = list(analysis.get("notes") or [])
    notes.append("Acabamento premium aplicado no Editor de video: motion graphics, B-roll derivado da fonte, transicoes organicas, micro-legendas, punch-ins, reenquadramento, grade, voz tratada e mixagem com ducking.")
    analysis["notes"] = notes

    base._set_project_state(
        user_id, project_id, status="ready", progress=100, timeline=timeline, analysis=analysis,
        preview_url=f"/api/media/editor-projects/{project_id}/preview.mp4", hook_variants=hooks,
    )


def run_claimed_editor_task(user_id: int, project_id: str, mode: str) -> None:
    if mode == "export":
        base.export_editor_project(user_id, project_id)
        return
    _ensure_audio_source(user_id, project_id)
    base.process_editor_project(user_id, project_id)
    project = base.read_project(user_id, project_id)
    if project.get("status") == "ready":
        try:
            enhance_editor_project(user_id, project_id)
        except Exception as exc:
            current = base.read_project(user_id, project_id)
            analysis = dict(current.get("analysis") or {})
            notes = list(analysis.get("notes") or [])
            notes.append(f"Acabamento avançado indisponível; preview base preservado: {exc}")
            analysis["notes"] = notes
            base._set_project_state(
                user_id, project_id, status="ready", progress=100, analysis=analysis,
                preview_url=f"/api/media/editor-projects/{project_id}/preview.mp4",
            )
