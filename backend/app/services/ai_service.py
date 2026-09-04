import re

from openai import OpenAI
from pydantic import BaseModel, Field

from ..config import settings
from .seo_service import normalize_clip_metadata


class ClipCandidate(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    hook: str
    reason: str
    title: str = Field(max_length=100)
    description: str
    copy: str = Field(max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=15)


class ClipPlan(BaseModel):
    clips: list[ClipCandidate]


class AIPlanningError(RuntimeError):
    pass


CLIP_SELECTION_TRANSCRIPT_LIMIT = 70000
CLIP_SELECTION_FALLBACK_LIMITS = (35000, 18000)
CLIP_SELECTION_TIME_BUCKETS = 12
SEGMENT_TEXT_LIMIT = 260

_LOCAL_HOOK_TERMS = {
    "como",
    "porque",
    "por que",
    "segredo",
    "verdade",
    "erro",
    "nunca",
    "sempre",
    "melhor",
    "pior",
    "importante",
    "resultado",
    "mudou",
    "topo",
    "obsessão",
    "dinheiro",
    "venda",
    "vendas",
    "cliente",
    "clientes",
    "estratégia",
    "aprendi",
    "descobri",
    "atenção",
    "imagine",
    "how",
    "why",
    "secret",
    "truth",
    "mistake",
    "never",
    "best",
    "important",
    "result",
}


def _segment_line(segment: dict) -> str:
    text = " ".join(str(segment.get("text") or "").split())
    if len(text) > SEGMENT_TEXT_LIMIT:
        text = text[: SEGMENT_TEXT_LIMIT - 1].rstrip() + "."
    return f"[{float(segment.get('start', 0.0)):.2f}-{float(segment.get('end', 0.0)):.2f}] {text}"


def _transcript_budget(limit: int | None = None) -> int:
    configured = int(limit if limit is not None else settings.max_transcript_chars)
    return max(8000, min(configured, CLIP_SELECTION_TRANSCRIPT_LIMIT))


def _distributed_transcript(segments: list[dict], budget: int) -> str:
    valid = [
        item
        for item in segments
        if item.get("text")
        and item.get("start") is not None
        and item.get("end") is not None
    ]
    if not valid:
        return ""

    start_time = min(float(item["start"]) for item in valid)
    end_time = max(float(item["end"]) for item in valid)
    duration = max(1.0, end_time - start_time)
    bucket_count = min(CLIP_SELECTION_TIME_BUCKETS, max(1, len(valid)))
    bucket_budget = max(1200, budget // bucket_count)
    output: list[str] = []

    for bucket in range(bucket_count):
        window_start = start_time + (duration * bucket / bucket_count)
        window_end = start_time + (duration * (bucket + 1) / bucket_count)
        is_last_bucket = bucket == bucket_count - 1
        chunk = []
        for item in valid:
            item_start = float(item["start"])
            in_window = window_start <= item_start < window_end
            in_last_window = (
                is_last_bucket and window_start <= item_start <= window_end
            )
            if in_window or in_last_window:
                chunk.append(item)
        if not chunk:
            continue

        used = 0
        if output:
            output.append("")
        output.append(
            f"[Excerpt {bucket + 1}/{bucket_count}: {window_start:.0f}s-{window_end:.0f}s]"
        )
        for segment in chunk:
            line = _segment_line(segment)
            next_used = used + len(line) + 1
            if next_used > bucket_budget and used > 0:
                break
            output.append(line)
            used = next_used

    text = "\n".join(output).strip()
    return text[:budget]


def _timestamped_transcript(
    segments: list[dict], limit: int | None = None
) -> str:
    budget = _transcript_budget(limit)
    lines = [
        _segment_line(s)
        for s in segments
        if s.get("text")
        and s.get("start") is not None
        and s.get("end") is not None
    ]
    text = "\n".join(lines)
    if len(text) <= budget:
        return text
    return _distributed_transcript(segments, budget)


def _is_rate_limit_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "rate_limit_exceeded" in lowered
        or "tokens per min" in lowered
        or "tpm" in lowered
    )


def _is_credit_or_quota_error(message: str) -> bool:
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "insufficient_quota",
            "credit_balance_exhausted",
            "no credits remaining",
            "quota exceeded",
            "billing",
        )
    )


def _clean_segments(segments: list[dict], duration: float) -> list[dict]:
    cleaned: list[dict] = []
    for item in segments:
        text = " ".join(str(item.get("text") or "").split())
        if not text:
            continue
        try:
            start = max(0.0, float(item.get("start", 0.0)))
            end = min(float(duration), float(item.get("end", 0.0)))
        except (TypeError, ValueError):
            continue
        if end <= start:
            continue
        cleaned.append({"start": start, "end": end, "text": text})
    cleaned.sort(key=lambda item: (item["start"], item["end"]))
    return cleaned


def _hook_from_text(text: str, fallback: str) -> str:
    compact = " ".join(text.split()).strip()
    if not compact:
        return fallback[:160].strip() or "Trecho em destaque"
    sentence = re.split(r"(?<=[.!?])\s+", compact, maxsplit=1)[0].strip()
    if len(sentence) < 18 and len(compact) > len(sentence):
        sentence = compact
    return sentence[:160].rstrip(" ,;:-")


def _local_score(text: str, clip_duration: float) -> float:
    lowered = text.casefold()
    words = re.findall(r"[\wÀ-ÿ]+", text, flags=re.UNICODE)
    density = len(words) / max(1.0, clip_duration)
    hook_hits = sum(1 for term in _LOCAL_HOOK_TERMS if term in lowered)
    punctuation = min(3, text.count("?") * 2 + text.count("!"))
    number_bonus = 1.0 if re.search(r"\b\d+([.,]\d+)?\b", text) else 0.0
    opening_bonus = 1.0 if len(words) >= 8 else 0.0
    return density * 2.0 + hook_hits * 2.5 + punctuation + number_bonus + opening_bonus


def _build_local_candidates(
    segments: list[dict], duration: float
) -> list[tuple[float, float, float, str]]:
    valid = _clean_segments(segments, duration)
    if not valid:
        return []

    candidates: list[tuple[float, float, float, str]] = []
    for start_index, first in enumerate(valid):
        start = first["start"]
        parts: list[str] = []
        end = first["end"]

        for item in valid[start_index:]:
            if item["start"] - end > 4.0 and parts:
                break
            end = max(end, item["end"])
            clip_duration = end - start
            if clip_duration > 60.0:
                break
            parts.append(item["text"])

            if clip_duration >= 20.0:
                text = " ".join(parts)
                duration_bonus = max(0.0, 3.0 - abs(38.0 - clip_duration) / 10.0)
                score = _local_score(text, clip_duration) + duration_bonus
                candidates.append((score, start, end, text))

            if clip_duration >= 48.0:
                break

    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates


def _select_clips_local(
    segments: list[dict],
    duration: float,
    requested_clips: int,
    source_title: str,
) -> list[ClipCandidate]:
    requested = max(1, int(requested_clips))
    ranked = _build_local_candidates(segments, duration)
    if not ranked:
        raise AIPlanningError(
            "No local clip candidates were found in the timestamped transcript"
        )

    selected: list[tuple[float, float, float, str]] = []
    for candidate in ranked:
        _, start, end, _ = candidate
        if any(
            start < existing_end + 1.0 and end > existing_start - 1.0
            for _, existing_start, existing_end, _ in selected
        ):
            continue
        selected.append(candidate)
        if len(selected) >= requested:
            break

    if len(selected) < requested:
        used_starts = {round(item[1], 1) for item in selected}
        for candidate in ranked:
            if round(candidate[1], 1) in used_starts:
                continue
            selected.append(candidate)
            used_starts.add(round(candidate[1], 1))
            if len(selected) >= requested:
                break

    selected.sort(key=lambda item: item[1])
    result: list[ClipCandidate] = []
    for _score, start, end, text in selected[:requested]:
        clip_duration = end - start
        if clip_duration < 15.0 or clip_duration > 60.0:
            continue

        hook = _hook_from_text(text, source_title)
        title_seed = hook or source_title or "Short em destaque"
        description_seed = (
            f"Trecho selecionado automaticamente de {source_title}. {hook}"
            if source_title
            else f"Trecho selecionado automaticamente. {hook}"
        ).strip()
        title, description, copy_text, tags = normalize_clip_metadata(
            title=title_seed,
            description=description_seed,
            copy_text="Qual a sua opinião sobre esse ponto? Comente e compartilhe.",
            tags=[],
            source_title=source_title,
            hook=hook,
        )
        result.append(
            ClipCandidate(
                start=round(start, 3),
                end=round(end, 3),
                hook=hook,
                reason=(
                    "Selecionado localmente por densidade de fala, clareza do "
                    "trecho e sinais de retenção, sem uso de API paga."
                ),
                title=title,
                description=description,
                copy=copy_text,
                tags=tags,
            )
        )

    if not result:
        raise AIPlanningError(
            "Local candidates were outside the required 15-60 second range"
        )
    return result


def _select_clips_openai(
    segments: list[dict],
    duration: float,
    requested_clips: int,
    source_title: str,
) -> list[ClipCandidate]:
    if not settings.openai_api_key:
        raise AIPlanningError("OPENAI_API_KEY is not configured")

    client = OpenAI(api_key=settings.openai_api_key)
    system = (
        "You are a senior YouTube Shorts editor and YouTube SEO strategist. Select self-contained, high-retention moments "
        "from a timestamped transcript. Each clip MUST be 15 to 60 seconds, start and end on sensible speech boundaries, "
        "avoid overlapping clips, and never invent timestamps or claims. Prefer an immediate hook, surprise, useful facts, "
        "emotional turns, concise explanations, controversy only when supported, or punchlines. "
        "For EVERY clip generate publication-ready metadata in the same language as the source: "
        "(1) a natural YouTube Shorts title, ideally 45-70 characters and never over 100, with the main search phrase early; "
        "(2) a useful SEO description whose first sentence clearly states the subject/search intent, followed by concise context "
        "and a natural engagement CTA; do not keyword-stuff; "
        "(3) a short engagement copy/CTA <= 500 characters; "
        "(4) 8-15 qualified YouTube tags without #, mixing the main topic, niche terms, specific long-tail phrases and close variants. "
        "Do not use unrelated trending keywords, deceptive clickbait, fabricated promises, or claims of guaranteed virality. "
        "Metadata must accurately match what is said inside that specific clip."
    )
    limits = (_transcript_budget(),) + tuple(
        limit
        for limit in CLIP_SELECTION_FALLBACK_LIMITS
        if limit < _transcript_budget()
    )
    plan = None
    last_error: Exception | None = None
    try:
        for index, limit in enumerate(limits):
            transcript = _timestamped_transcript(segments, limit)
            if not transcript:
                raise AIPlanningError("No timestamped transcript available")
            user = (
                f"Source title: {source_title}\n"
                f"Video duration: {duration:.2f}s\n"
                f"Return exactly {requested_clips} clips when the transcript has enough suitable moments.\n"
                "Choose only moments present in the timestamped transcript excerpts below.\n\n"
                f"TIMESTAMPED TRANSCRIPT EXCERPTS:\n{transcript}"
            )
            try:
                response = client.responses.parse(
                    model=settings.openai_text_model,
                    input=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    text_format=ClipPlan,
                )
                plan = response.output_parsed
                break
            except Exception as exc:
                last_error = exc
                if index < len(limits) - 1 and _is_rate_limit_error(str(exc)):
                    continue
                raise
    except AIPlanningError:
        raise
    except Exception as exc:
        exc = last_error or exc
        raise AIPlanningError(f"OpenAI clip selection failed: {exc}") from exc

    if not plan or not plan.clips:
        raise AIPlanningError("OpenAI returned no clip candidates")

    cleaned: list[ClipCandidate] = []
    for clip in plan.clips:
        start = max(0.0, min(float(clip.start), duration))
        end = max(0.0, min(float(clip.end), duration))
        clip_len = end - start
        if clip_len < 15 or clip_len > 60:
            continue

        title, description, copy_text, tags = normalize_clip_metadata(
            title=clip.title,
            description=clip.description,
            copy_text=clip.copy,
            tags=clip.tags,
            source_title=source_title,
            hook=clip.hook,
        )
        clip.start = round(start, 3)
        clip.end = round(end, 3)
        clip.title = title
        clip.description = description
        clip.copy = copy_text
        clip.tags = tags
        cleaned.append(clip)
        if len(cleaned) >= requested_clips:
            break

    if not cleaned:
        raise AIPlanningError(
            "OpenAI candidates were outside the required 15-60 second range"
        )
    return cleaned


def select_clips(
    segments: list[dict],
    duration: float,
    requested_clips: int,
    source_title: str,
) -> list[ClipCandidate]:
    provider = (settings.clip_planning_provider or "local").strip().lower()
    if provider not in {"local", "openai", "auto"}:
        raise AIPlanningError(
            "CLIP_PLANNING_PROVIDER must be one of: local, openai, auto"
        )

    if provider == "local":
        return _select_clips_local(
            segments, duration, requested_clips, source_title
        )

    if provider == "openai":
        return _select_clips_openai(
            segments, duration, requested_clips, source_title
        )

    if not settings.openai_api_key:
        return _select_clips_local(
            segments, duration, requested_clips, source_title
        )

    try:
        return _select_clips_openai(
            segments, duration, requested_clips, source_title
        )
    except AIPlanningError as exc:
        message = str(exc)
        if _is_credit_or_quota_error(message) or _is_rate_limit_error(message):
            return _select_clips_local(
                segments, duration, requested_clips, source_title
            )
        raise
