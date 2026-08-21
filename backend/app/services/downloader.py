import json
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from yt_dlp import YoutubeDL
from ..config import settings

VISITOR_DATA_FILE = settings.data_path / "youtube_visitor_data.txt"


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


def _provider_visitor_data() -> str | None:
    if not settings.ytdlp_pot_provider_url:
        return None
    if VISITOR_DATA_FILE.exists():
        cached = VISITOR_DATA_FILE.read_text(encoding="utf-8").strip()
        if cached:
            return cached

    request = Request(
        urljoin(settings.ytdlp_pot_provider_url.rstrip("/") + "/", "get_pot"),
        data=b"{}",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    content_binding = str(payload.get("contentBinding") or "").strip()
    if content_binding:
        VISITOR_DATA_FILE.write_text(content_binding, encoding="utf-8")
        return content_binding
    return None


def _pot_provider_args() -> dict | None:
    if not settings.ytdlp_pot_provider_url:
        return None
    youtube_args = {
        "player_client": ["mweb"],
        "player_skip": ["webpage", "configs"],
    }
    try:
        visitor_data = _provider_visitor_data()
    except Exception:
        visitor_data = None
    if visitor_data:
        youtube_args["visitor_data"] = [visitor_data]
    return {
        "extractor_args": {
            "youtube": youtube_args,
            "youtubetab": {"skip": ["webpage"]},
            "youtubepot-bgutilhttp": {"base_url": [settings.ytdlp_pot_provider_url]},
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


def download_video(url: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    option_variants = [
        _pot_provider_args(),
        {"extractor_args": {"youtube": {"player_client": ["web_embedded"], "player_skip": ["webpage", "configs"]}}},
        {"extractor_args": {"youtube": {"player_client": ["tv", "web_safari"]}}},
        {},
    ]
    errors: list[str] = []
    try:
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
                errors.append(str(exc))
    except Exception as exc:
        raise DownloadError(f"yt-dlp failed: {exc}") from exc

    if errors:
        raise DownloadError(f"yt-dlp failed after {len(errors)} attempts: {' | '.join(errors)}")

    raise DownloadError("yt-dlp finished without producing a video file")
