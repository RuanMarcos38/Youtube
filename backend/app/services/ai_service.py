from openai import OpenAI
from pydantic import BaseModel, Field
from ..config import settings


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


def _timestamped_transcript(segments: list[dict]) -> str:
    lines = [f"[{s['start']:.2f}-{s['end']:.2f}] {s['text']}" for s in segments if s.get("text")]
    text = "\n".join(lines)
    return text[: settings.max_transcript_chars]


def select_clips(segments: list[dict], duration: float, requested_clips: int, source_title: str) -> list[ClipCandidate]:
    if not settings.openai_api_key:
        raise AIPlanningError("OPENAI_API_KEY is not configured")

    transcript = _timestamped_transcript(segments)
    if not transcript:
        raise AIPlanningError("No timestamped transcript available")

    client = OpenAI(api_key=settings.openai_api_key)
    system = (
        "You are a senior short-form video editor. Select self-contained, high-retention moments from a timestamped transcript. "
        "Each clip MUST be 15 to 60 seconds, start and end on sensible speech boundaries, avoid overlapping clips, and never invent timestamps. "
        "Prefer strong hooks, surprise, useful facts, emotional turns, concise explanations or punchlines. "
        "Generate a YouTube Shorts title <= 100 characters, a useful description ending with #Shorts, a short engagement copy/CTA <= 500 characters, and 3-10 relevant tags. "
        "Do not make deceptive claims that are not supported by the transcript."
    )
    user = (
        f"Source title: {source_title}\n"
        f"Video duration: {duration:.2f}s\n"
        f"Return exactly {requested_clips} clips when the transcript has enough suitable moments.\n\n"
        f"TIMESTAMPED TRANSCRIPT:\n{transcript}"
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
    except Exception as exc:
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
        clip.start = round(start, 3)
        clip.end = round(end, 3)
        clip.title = clip.title.strip()[:100] or "Short em destaque"
        clip.tags = [tag.strip().lstrip("#") for tag in clip.tags if tag.strip()][:15]
        cleaned.append(clip)
        if len(cleaned) >= requested_clips:
            break

    if not cleaned:
        raise AIPlanningError("OpenAI candidates were outside the required 15-60 second range")
    return cleaned
