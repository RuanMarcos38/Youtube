import importlib.util
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen

from fastapi import APIRouter
from ..config import settings
from ..database import SessionLocal
from ..models import YouTubeConnection
from ..services.downloader import download_access_configured, download_auth_configured, download_proxy_configured
from ..services.youtube_oauth import oauth_configured

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


def _js_runtime_available() -> bool:
    configured = settings.ytdlp_node_path.strip()
    if configured:
        return Path(configured).is_file()
    return bool(shutil.which("node"))


def _ejs_available() -> bool:
    return importlib.util.find_spec("yt_dlp_ejs") is not None


def _connected_profiles() -> int:
    db = SessionLocal()
    try:
        return db.query(YouTubeConnection).filter(YouTubeConnection.token_json.isnot(None)).count()
    except Exception:
        return 0
    finally:
        db.close()


@router.get("/health")
def health():
    connected_profiles = _connected_profiles()
    checks = {
        "openai_configured": bool(settings.openai_api_key),
        "youtube_api_configured": bool(settings.youtube_api_key),
        "google_oauth_configured": oauth_configured(),
        "youtube_connected_profiles": connected_profiles,
        "ffmpeg_available": bool(shutil.which(settings.ffmpeg_binary)),
        "ffprobe_available": bool(shutil.which(settings.ffprobe_binary)),
        "worker_alive": _worker_alive(),
        "pot_provider_alive": _pot_provider_alive(),
        "ytdlp_js_runtime_available": _js_runtime_available(),
        "ytdlp_ejs_available": _ejs_available(),
        "youtube_download_auth_configured": download_auth_configured(),
        "youtube_download_proxy_configured": download_proxy_configured(),
        "youtube_download_ready": download_access_configured(),
    }

    required_runtime = [
        checks["ffmpeg_available"],
        checks["ffprobe_available"],
        checks["worker_alive"],
        checks["ytdlp_js_runtime_available"],
        checks["ytdlp_ejs_available"],
    ]
    if settings.ytdlp_pot_provider_url:
        required_runtime.append(checks["pot_provider_alive"])

    required_configuration = [
        checks["openai_configured"],
        checks["youtube_api_configured"],
        checks["google_oauth_configured"],
        checks["youtube_download_ready"],
        *required_runtime,
    ]

    auth_mode = "guest"
    if checks["youtube_download_auth_configured"] and checks["youtube_download_proxy_configured"]:
        auth_mode = "cookies+proxy"
    elif checks["youtube_download_auth_configured"]:
        auth_mode = "cookies"
    elif checks["youtube_download_proxy_configured"]:
        auth_mode = "proxy"

    return {
        "status": "ok" if all(required_runtime) else "degraded",
        "configuration_complete": all(required_configuration),
        "app": settings.app_name,
        "version": "2.0.0",
        "checks": checks,
        "youtube_download_mode": auth_mode,
        "oauth_redirect_uri": settings.youtube_oauth_redirect_uri,
    }
