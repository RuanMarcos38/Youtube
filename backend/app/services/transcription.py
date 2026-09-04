import math
import os
from collections.abc import Callable
from pathlib import Path
from threading import BoundedSemaphore, Lock

from faster_whisper import WhisperModel
from openai import OpenAI

from ..config import settings


class TranscriptionError(RuntimeError):
    pass


ProgressHook = Callable[[int, int, Path], None]

_MODEL: WhisperModel | None = None
_MODEL_KEY: tuple[str, str, str, int, int] | None = None
_MODEL_INIT_LOCK = Lock()


def _cgroup_cpu_limit() -> int | None:
    """Best-effort CPU quota detection for Docker/EasyPanel containers."""
    try:
        cpu_max = Path("/sys/fs/cgroup/cpu.max")
        if cpu_max.exists():
            quota_text, period_text = cpu_max.read_text(encoding="utf-8").strip().split()[:2]
            if quota_text != "max":
                quota = int(quota_text)
                period = max(1, int(period_text))
                return max(1, math.ceil(quota / period))
    except Exception:
        pass

    try:
        quota_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        period_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        if quota_path.exists() and period_path.exists():
            quota = int(quota_path.read_text(encoding="utf-8").strip())
            period = max(1, int(period_path.read_text(encoding="utf-8").strip()))
            if quota > 0:
                return max(1, math.ceil(quota / period))
    except Exception:
        pass
    return None


def _available_cpu_threads() -> int:
    host = max(1, int(os.cpu_count() or 1))
    cgroup = _cgroup_cpu_limit()
    return min(host, cgroup) if cgroup else host


def _parallelism() -> int:
    requested = max(1, min(int(settings.local_whisper_parallelism or 1), 5))
    available = _available_cpu_threads()
    # Give each Whisper inference at least ~2 CPU threads when possible. Five
    # videos remain active in the pipeline, but the heaviest stage is bounded to
    # what the actual EasyPanel CPU quota can sustain without thrashing.
    safe_for_cpu = max(1, available // 2)
    return max(1, min(requested, safe_for_cpu))


def _cpu_threads_per_transcription() -> int:
    configured = int(settings.local_whisper_cpu_threads or 0)
    if configured > 0:
        return max(1, configured)
    available = _available_cpu_threads()
    return max(1, available // _parallelism())


_TRANSCRIBE_SLOTS = BoundedSemaphore(_parallelism())


def _get_local_model() -> WhisperModel:
    global _MODEL, _MODEL_KEY

    model_name = (settings.local_whisper_model or "small").strip()
    device = (settings.local_whisper_device or "cpu").strip()
    compute_type = (settings.local_whisper_compute_type or "int8").strip()
    cpu_threads = _cpu_threads_per_transcription()
    num_workers = _parallelism()
    key = (model_name, device, compute_type, cpu_threads, num_workers)

    with _MODEL_INIT_LOCK:
        if _MODEL is not None and _MODEL_KEY == key:
            return _MODEL

        download_root = settings.data_path / "models" / "faster-whisper"
        download_root.mkdir(parents=True, exist_ok=True)
        try:
            _MODEL = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                cpu_threads=cpu_threads,
                num_workers=num_workers,
                download_root=str(download_root),
            )
            _MODEL_KEY = key
            return _MODEL
        except Exception as exc:
            raise TranscriptionError(
                f"Local Faster-Whisper model could not be loaded ({model_name}/{device}/{compute_type}): {exc}"
            ) from exc


def _transcribe_local(
    audio_files: list[Path],
    segment_seconds: int,
    progress_hook: ProgressHook | None,
) -> tuple[str, list[dict]]:
    model = _get_local_model()
    all_segments: list[dict] = []
    text_parts: list[str] = []
    total = len(audio_files)
    language = (settings.local_whisper_language or "").strip() or None

    for index, audio_path in enumerate(audio_files):
        offset = index * segment_seconds
        if progress_hook:
            progress_hook(index, total, audio_path)

        try:
            # CTranslate2 supports parallel generation through num_workers. The
            # semaphore keeps CPU-heavy calls bounded while other pipeline
            # stages continue for up to five videos.
            with _TRANSCRIBE_SLOTS:
                chunk_segments, _info = model.transcribe(
                    str(audio_path),
                    language=language,
                    beam_size=max(1, int(settings.local_whisper_beam_size)),
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 500},
                    condition_on_previous_text=False,
                    temperature=0.0,
                    word_timestamps=False,
                )
                chunk_segments = list(chunk_segments)
        except Exception as exc:
            raise TranscriptionError(
                f"Local Faster-Whisper transcription failed for {audio_path.name}: {exc}"
            ) from exc

        chunk_text: list[str] = []
        for segment in chunk_segments:
            text = str(getattr(segment, "text", "") or "").strip()
            if text:
                chunk_text.append(text)
            all_segments.append(
                {
                    "start": float(getattr(segment, "start", 0.0)) + offset,
                    "end": float(getattr(segment, "end", 0.0)) + offset,
                    "text": text,
                }
            )
        text_parts.append(" ".join(chunk_text).strip())

        if progress_hook:
            progress_hook(index + 1, total, audio_path)

    if not all_segments and any(text_parts):
        raise TranscriptionError("Local transcription returned text but no timestamps")
    return "\n".join(part for part in text_parts if part).strip(), all_segments


def _transcribe_openai(
    audio_files: list[Path],
    segment_seconds: int,
    progress_hook: ProgressHook | None,
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
                transcript = client.audio.transcriptions.create(
                    model=settings.openai_transcription_model,
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["segment"],
                )
        except Exception as exc:
            raise TranscriptionError(
                f"OpenAI transcription failed for {audio_path.name}: {exc}"
            ) from exc

        text = getattr(transcript, "text", "") or ""
        text_parts.append(text)
        segments = getattr(transcript, "segments", None) or []
        for segment in segments:
            if hasattr(segment, "model_dump"):
                item = segment.model_dump()
            elif isinstance(segment, dict):
                item = segment
            else:
                item = {
                    "start": getattr(segment, "start", 0.0),
                    "end": getattr(segment, "end", 0.0),
                    "text": getattr(segment, "text", ""),
                }
            all_segments.append(
                {
                    "start": float(item.get("start", 0.0)) + offset,
                    "end": float(item.get("end", 0.0)) + offset,
                    "text": str(item.get("text", "")).strip(),
                }
            )
        if progress_hook:
            progress_hook(index + 1, total, audio_path)

    if not all_segments and text_parts:
        raise TranscriptionError(
            "Transcription returned text but no timestamps. Keep "
            "OPENAI_TRANSCRIPTION_MODEL=whisper-1 for timestamped editing."
        )
    return "\n".join(text_parts).strip(), all_segments


def transcribe_chunks(
    audio_files: list[Path],
    segment_seconds: int = 600,
    progress_hook: ProgressHook | None = None,
) -> tuple[str, list[dict]]:
    provider = (settings.transcription_provider or "local").strip().lower()
    if provider not in {"local", "openai", "auto"}:
        raise TranscriptionError(
            "TRANSCRIPTION_PROVIDER must be one of: local, openai, auto"
        )

    if provider == "openai":
        return _transcribe_openai(audio_files, segment_seconds, progress_hook)

    try:
        return _transcribe_local(audio_files, segment_seconds, progress_hook)
    except TranscriptionError as local_error:
        # No paid API call is made unless this is explicitly enabled. The
        # production default remains local-only to guarantee zero API cost.
        should_fallback = (
            provider == "auto" or settings.allow_openai_transcription_fallback
        )
        if should_fallback and settings.openai_api_key:
            try:
                return _transcribe_openai(
                    audio_files, segment_seconds, progress_hook
                )
            except TranscriptionError as openai_error:
                raise TranscriptionError(
                    f"{local_error}; OpenAI fallback also failed: {openai_error}"
                ) from openai_error
        raise
