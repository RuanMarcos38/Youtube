import shutil
from datetime import datetime, timezone
from urllib.parse import urljoin
from urllib.request import urlopen

from fastapi import APIRouter
from ..config import settings
from ..services.youtube_oauth import get_connection_status

router = APIRouter(tags=["system"])


def _worker_alive() -> bool:
    heartbeat = settings.data_path / "worker_heartbeat.txt"
    if not heartbeat.exists():
        return False
    try:
        value = datetime.fromisoformat(heartbeat.read_text(encoding="utf-8").strip())
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - value).total_seconds() < 20
    except Exception:
        return False


def _pot_provider_alive() -> bool:
    if not settings.ytdlp_pot_provider_url:
        return False
    try:
        endpoint = urljoin(settings.ytdlp_pot_provider_url.rstrip("/") + "/", "ping")
        with urlopen(endpoint, timeout=2) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


@router.get("/health")
def health():
    youtube = get_connection_status()
    checks = {
        "openai_configured": bool(settings.openai_api_key),
        "youtube_api_configured": bool(settings.youtube_api_key),
        "google_oauth_configured": youtube["configured"],
        "youtube_channel_connected": youtube["connected"],
        "ffmpeg_available": bool(shutil.which(settings.ffmpeg_binary)),
        "ffprobe_available": bool(shutil.which(settings.ffprobe_binary)),
        "worker_alive": _worker_alive(),
        "pot_provider_alive": _pot_provider_alive(),
    }
    required_runtime = [
        checks["ffmpeg_available"],
        checks["ffprobe_available"],
        checks["worker_alive"],
    ]
    if settings.ytdlp_pot_provider_url:
        required_runtime.append(checks["pot_provider_alive"])
    return {
        "status": "ok" if all(required_runtime) else "degraded",
        "configuration_complete": all(checks.values()),
        "app": settings.app_name,
        "checks": checks,
        "youtube_channel": {
            "id": youtube.get("channel_id"),
            "title": youtube.get("channel_title"),
        },
        "oauth_redirect_uri": youtube["redirect_uri"],
    }
