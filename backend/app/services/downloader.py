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
        "source_address": "0.0.0.0",
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
    }
    if settings.ytdlp_cookie_file:
        options["cookiefile"] = settings.ytdlp_cookie_file
    return options


def _pot_provider_args(player_client: str = "mweb") -> dict | None:
    if not settings.ytdlp_pot_provider_url:
        return None
    return {
        "extractor_args": {
            "youtube": {
                "player_client": [player_client],
                "fetch_pot": ["always"],
            },
            "youtubepot-bgutilhttp": {
                "base_url": [settings.ytdlp_pot_provider_url],
            },
        }
    }


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


def _compact_error(message: str) -> str:
    text = " ".join(str(message).split())
    if len(text) > 500:
        return text[:497] + "..."
    return text


def download_video(url: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Keep each YouTube client isolated. Mixing clients in one extraction can
    # produce a PO token for one client and a media URL belonging to another.
    option_variants = [
        _pot_provider_args("mweb"),
        _pot_provider_args("web_safari"),
        {
            "extractor_args": {
                "youtube": {
                    "player_client": ["web_embedded"],
                }
            }
        },
        {},
    ]

    errors: list[str] = []
    for variant in option_variants:
        if variant is None:
            continue
        options = _base_options(output_dir)
        options.update(variant)
        try:
            video_path = _download_with_options(url, output_dir, options)
            if video_path:
                return video_path
        except Exception as exc:
            error = _compact_error(str(exc))
            if error and error not in errors:
                errors.append(error)

    if errors:
        bot_blocked = any(
            "Sign in to confirm you're not a bot" in error
            or "Sign in to confirm you’re not a bot" in error
            for error in errors
        )
        suffix = (
            " The VPS IP is still being challenged by YouTube even after a fresh PO Token. "
            "If this persists, configure an authorized YouTube cookie file or a clean egress proxy."
            if bot_blocked
            else ""
        )
        raise DownloadError(
            f"yt-dlp failed after {len(errors)} strategies: {' | '.join(errors)}{suffix}"
        )

    raise DownloadError("yt-dlp finished without producing a video file")
