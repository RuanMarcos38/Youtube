from collections.abc import Callable
from pathlib import Path

from openai import OpenAI
from ..config import settings


class TranscriptionError(RuntimeError):
    pass


ProgressHook = Callable[[int, int, Path], None]


def transcribe_chunks(
    audio_files: list[Path],
    segment_seconds: int = 600,
    progress_hook: ProgressHook | None = None,
) -> tuple[str, list[dict]]:
    if not settings.openai_api_key:
        raise TranscriptionError("OPENAI_API_KEY is not configured")
    client = OpenAI(api_key=settings.openai_api_key)
    all_segments: list[dict] = []
    text_parts: list[str] = []
    total = len(audio_files)
    for index, audio_path in enumerate(audio_files):
        offset = index * segment_seconds
        if progress_hook:
            progress_hook(index, total, audio_path)
        try:
            with audio_path.open("rb") as audio_file:
                transcript = client.audio.transcriptions.create(model=settings.openai_transcription_model,file=audio_file,response_format="verbose_json",timestamp_granularities=["segment"])
        except Exception as exc:
            raise TranscriptionError(f"OpenAI transcription failed for {audio_path.name}: {exc}") from exc
        text = getattr(transcript, "text", "") or ""
        text_parts.append(text)
        segments = getattr(transcript, "segments", None) or []
        for segment in segments:
            if hasattr(segment, "model_dump"):
                item = segment.model_dump()
            elif isinstance(segment, dict):
                item = segment
            else:
                item = {"start": getattr(segment, "start", 0.0),"end": getattr(segment, "end", 0.0),"text": getattr(segment, "text", "")}
            all_segments.append({"start": float(item.get("start", 0.0)) + offset,"end": float(item.get("end", 0.0)) + offset,"text": str(item.get("text", "")).strip()})
        if progress_hook:
            progress_hook(index + 1, total, audio_path)
    if not all_segments and text_parts:
        raise TranscriptionError("Transcription returned text but no timestamps. Keep OPENAI_TRANSCRIPTION_MODEL=whisper-1 for timestamped editing.")
    return "\n".join(text_parts).strip(), all_segments
