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


def _segment_line(segment: dict) -> str:
    text = " ".join(str(segment.get("text") or "").split())
    if len(text) > SEGMENT_TEXT_LIMIT:
        text = text[: SEGMENT_TEXT_LIMIT - 1].rstrip() + "."
    return f"[{float(segment.get('start', 0.0)):.2f}-{float(segment.get('end', 0.0)):.2f}] {text}"


def _transcript_budget(limit: int | None = None) -> int:
    configured = int(limit if limit is not None else settings.max_transcript_chars)
    return max(8000, min(configured, CLIP_SELECTION_TRANSCRIPT_LIMIT))


def _distributed_transcript(segments: list[dict], budget: int) -> str:
    valid = [item for item in segments if item.get("text") and item.get("start") is not None and item.get("end") is not None]
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
            in_last_window = is_last_bucket and window_start <= item_start <= window_end
            if in_window or in_last_window:
                chunk.append(item)
        if not chunk:
            continue

        used = 0
        if output:
            output.append("")
        output.append(f"[Excerpt {bucket + 1}/{bucket_count}: {window_start:.0f}s-{window_end:.0f}s]")
        for segment in chunk:
            line = _segment_line(segment)
            next_used = used + len(line) + 1
            if next_used > bucket_budget and used > 0:
                break
            output.append(line)
            used = next_used

    text = "\n".join(output).strip()
    return text[:budget]


def _timestamped_transcript(segments: list[dict], limit: int | None = None) -> str:
    budget = _transcript_budget(limit)
    lines = [_segment_line(s) for s in segments if s.get("text") and s.get("start") is not None and s.get("end") is not None]
    text = "\n".join(lines)
    if len(text) <= budget:
        return text
    return _distributed_transcript(segments, budget)


def _is_rate_limit_error(message: str) -> bool:
    lowered = message.lower()
    return "rate_limit_exceeded" in lowered or "tokens per min" in lowered or "tpm" in lowered


def select_clips(segments: list[dict], duration: float, requested_clips: int, source_title: str) -> list[ClipCandidate]:
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
    limits = (_transcript_budget(),) + tuple(limit for limit in CLIP_SELECTION_FALLBACK_LIMITS if limit < _transcript_budget())
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
        raise AIPlanningError("OpenAI candidates were outside the required 15-60 second range")
    return cleaned
