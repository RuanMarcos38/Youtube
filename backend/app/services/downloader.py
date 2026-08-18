from pathlib import Path
from yt_dlp import YoutubeDL
from ..config import settings


class DownloadError(RuntimeError):
    pass


def download_video(url: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    options = {
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

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            requested = info.get("requested_downloads") or []
            candidates = [Path(item.get("filepath", "")) for item in requested if item.get("filepath")]
            candidates += list(output_dir.glob("source.*"))
            mp4 = output_dir / "source.mp4"
            if mp4.exists():
                return mp4
            for candidate in candidates:
                if candidate.exists() and candidate.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}:
                    return candidate
    except Exception as exc:
        raise DownloadError(f"yt-dlp failed: {exc}") from exc

    raise DownloadError("yt-dlp finished without producing a video file")
