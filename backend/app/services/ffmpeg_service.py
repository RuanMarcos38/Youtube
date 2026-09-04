from pathlib import Path
import subprocess
from ..config import settings


class FFmpegError(RuntimeError):
    pass


def _run(command: list[str]) -> str:
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return result.stdout
    except FileNotFoundError as exc:
        raise FFmpegError(f"Executable not found: {command[0]}. Install FFmpeg and add it to PATH.") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "Unknown FFmpeg error")[-5000:]
        raise FFmpegError(details) from exc


def ensure_ffmpeg() -> None:
    _run([settings.ffmpeg_binary, "-version"])
    _run([settings.ffprobe_binary, "-version"])


def get_duration(video_path: Path) -> float:
    output = _run([
        settings.ffprobe_binary,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ])
    return float(output.strip())


def extract_audio_chunks(video_path: Path, output_dir: Path, segment_seconds: int = 600) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "audio_%03d.mp3"
    _run([
        settings.ffmpeg_binary, "-y",
        "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k",
        "-f", "segment", "-segment_time", str(segment_seconds), "-reset_timestamps", "1",
        str(pattern),
    ])
    files = sorted(output_dir.glob("audio_*.mp3"))
    if not files:
        raise FFmpegError("Audio extraction did not create any chunks")
    return files


def _srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def write_clip_srt(segments: list[dict], clip_start: float, clip_end: float, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    index = 1
    for segment in segments:
        start = float(segment.get("start", 0.0))
        end = float(segment.get("end", 0.0))
        text = str(segment.get("text", "")).strip()
        if not text or end <= clip_start or start >= clip_end:
            continue
        local_start = max(start, clip_start) - clip_start
        local_end = min(end, clip_end) - clip_start
        if local_end <= local_start:
            continue
        lines.extend([
            str(index),
            f"{_srt_timestamp(local_start)} --> {_srt_timestamp(local_end)}",
            text,
            "",
        ])
        index += 1
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _escape_filter_path(path: Path) -> str:
    # FFmpeg filter syntax needs special escaping, especially for Windows drive letters.
    value = path.resolve().as_posix().replace("\\", "/")
    value = value.replace(":", r"\:").replace("'", r"\'")
    return value


def _subtitle_force_style(caption_position: str, caption_margin_v: int, caption_font_size: int) -> str:
    alignment = {
        "top": 8,
        "middle": 5,
        "bottom": 2,
    }.get(caption_position, 2)
    margin = max(40, min(760, int(caption_margin_v or 120)))
    font_size = max(14, min(32, int(caption_font_size or 18)))
    return (
        "FontName=Arial,"
        f"FontSize={font_size},"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BackColour=&H70000000,"
        "BorderStyle=1,"
        "Outline=3,"
        "Shadow=1,"
        f"Alignment={alignment},"
        f"MarginV={margin}"
    )


def render_vertical_clip(
    source_path: Path,
    output_path: Path,
    start_seconds: float,
    end_seconds: float,
    subtitle_path: Path | None = None,
    *,
    caption_position: str = "bottom",
    caption_margin_v: int = 120,
    caption_font_size: int = 18,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.1, end_seconds - start_seconds)

    filters = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2",
    ]
    if subtitle_path and subtitle_path.exists() and subtitle_path.stat().st_size > 0:
        escaped = _escape_filter_path(subtitle_path)
        style = _subtitle_force_style(caption_position, caption_margin_v, caption_font_size)
        filters.append(f"subtitles='{escaped}':force_style='{style}'")

    preset = (settings.ffmpeg_preset or "veryfast").strip()
    if preset not in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}:
        preset = "veryfast"
    crf = max(16, min(30, int(settings.ffmpeg_crf or 21)))
    threads = max(1, min(8, int(settings.ffmpeg_threads_per_job or 2)))

    _run([
        settings.ffmpeg_binary, "-y",
        "-ss", f"{start_seconds:.3f}",
        "-i", str(source_path),
        "-t", f"{duration:.3f}",
        "-vf", ",".join(filters),
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
        "-threads", str(threads),
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(output_path),
    ])
    return output_path
