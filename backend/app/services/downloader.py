from pathlib import Path
from yt_dlp import YoutubeDL
from ..config import settings


class DownloadError(RuntimeError):
    pass


def _base_options(output_dir: Path) -> dict:
    options: dict = {
        "outtmpl": str(output_dir / "source.%(ext)s"),
        "format": "bv*[height<=1080]+ba/b[height<=1080]/best",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
        "overwrites": True,
        "restrictfilenames": True,
    }
    if settings.ytdlp_cookie_file:
        options["cookiefile"] = settings.ytdlp_cookie_file
    return options


def _find_downloaded_file(output_dir: Path, info: dict) -> Path | None:
    requested = info.get("requested_downloads") or []
    candidates = [Path(item.get("filepath", "")) for item in requested if item.get("filepath")]
    candidates += list(output_dir.glob("source.*"))
    mp4 = output_dir / "source.mp4"
    if mp4.exists():
        return mp4
    for candidate in candidates:
        if candidate.exists() and candidate.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}:
            return candidate
    return None


def _download_with_options(url: str, output_dir: Path, options: dict) -> Path | None:
    with YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)
    return _find_downloaded_file(output_dir, info)


def download_video(url: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    option_variants = [
        {},
        {"extractor_args": {"youtube": {"player_client": ["tv", "web_safari"]}}},
    ]
    errors: list[str] = []
    try:
        for variant in option_variants:
            options = _base_options(output_dir)
            options.update(variant)
            try:
                video_path = _download_with_options(url, output_dir, options)
                if video_path:
                    return video_path
            except Exception as exc:
                errors.append(str(exc))
    except Exception as exc:
        raise DownloadError(f"yt-dlp failed: {exc}") from exc

    if errors:
        raise DownloadError(f"yt-dlp failed after {len(errors)} attempts: {' | '.join(errors)}")

    raise DownloadError("yt-dlp finished without producing a video file")
