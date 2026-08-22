import importlib.util
import shutil
from datetime import datetime, timezone
from urllib.parse import urljoin
from urllib.request import urlopen

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Job, YouTubeConnection
from .downloader import js_runtime_status, validate_download_session
from .runtime_download_auth import COOKIE_OVERRIDE_FILE, PROXY_OVERRIDE_FILE
from .youtube_oauth import get_connection_status, oauth_configured


ACTIVE_JOB_STATES = {
    "queued",
    "preparing",
    "downloading",
    "extracting_audio",
    "transcribing",
    "selecting_clips",
    "rendering",
    "captioning",
}


def _worker_alive() -> bool:
    heartbeat = settings.data_path / "worker_heartbeat.txt"
    if not heartbeat.exists():
        return False
    try:
        value = datetime.fromisoformat(heartbeat.read_text(encoding="utf-8").strip())
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - value).total_seconds() < 25
    except Exception:
        return False


def _pot_provider_alive() -> bool:
    if not settings.ytdlp_pot_provider_url:
        return False
    try:
        endpoint = urljoin(settings.ytdlp_pot_provider_url.rstrip("/") + "/", "ping")
        with urlopen(endpoint, timeout=3) as response:
            return 200 <= response.status < 300
    except Exception:
        return False


def _cleanup_invalid_runtime_overrides() -> list[str]:
    fixes: list[str] = []
    for path, label in (
        (COOKIE_OVERRIDE_FILE, "cookie override vazio"),
        (PROXY_OVERRIDE_FILE, "proxy override vazio"),
    ):
        try:
            if path.exists() and path.stat().st_size == 0:
                path.unlink(missing_ok=True)
                fixes.append(f"Removido {label}.")
        except Exception:
            pass
    settings.data_path.mkdir(parents=True, exist_ok=True)
    settings.sqlite_file.parent.mkdir(parents=True, exist_ok=True)
    return fixes


def _check(name: str, ok: bool, detail: str, *, required: bool = True, recommendation: str = "") -> dict:
    return {
        "name": name,
        "ok": bool(ok),
        "required": required,
        "detail": detail,
        "recommendation": recommendation if not ok else "",
    }


def run_self_test(db: Session, *, auto_fix: bool = True) -> dict:
    fixes_applied = _cleanup_invalid_runtime_overrides() if auto_fix else []
    checks: list[dict] = []

    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        db_ok = False
        db_error = str(exc)
    checks.append(_check("Banco de dados", db_ok, "Conexão SQL respondendo." if db_ok else db_error, recommendation="Revisar DATABASE_URL/SQLite do serviço shortsia."))

    worker_ok = _worker_alive()
    checks.append(_check("Worker", worker_ok, "Heartbeat ativo." if worker_ok else "Heartbeat do worker não foi encontrado ou está atrasado.", recommendation="O Supervisor deve reiniciar o worker; verifique os logs do serviço se continuar inativo."))

    ffmpeg_ok = bool(shutil.which(settings.ffmpeg_binary))
    ffprobe_ok = bool(shutil.which(settings.ffprobe_binary))
    checks.append(_check("FFmpeg", ffmpeg_ok, "FFmpeg disponível." if ffmpeg_ok else "FFmpeg não encontrado.", recommendation="Reconstruir a imagem Docker oficial do ShortsFlow."))
    checks.append(_check("FFprobe", ffprobe_ok, "FFprobe disponível." if ffprobe_ok else "FFprobe não encontrado.", recommendation="Reconstruir a imagem Docker oficial do ShortsFlow."))

    checks.append(_check("OpenAI", bool(settings.openai_api_key), "API key configurada." if settings.openai_api_key else "API key ausente.", recommendation="Configure OPENAI_API_KEY apenas no ambiente seguro do EasyPanel."))
    checks.append(_check("YouTube Data API", bool(settings.youtube_api_key), "API key configurada." if settings.youtube_api_key else "API key ausente.", recommendation="Configure YOUTUBE_API_KEY no EasyPanel."))
    checks.append(_check("Google OAuth", oauth_configured(), "Cliente OAuth configurado." if oauth_configured() else "Cliente OAuth ausente.", recommendation="Configure o Client ID/Secret e mantenha o app Google em Produção para contas externas."))

    runtime = js_runtime_status()
    js_ok = bool(runtime.get("node") or runtime.get("deno"))
    checks.append(_check("Runtime JavaScript yt-dlp", js_ok, f"Node={bool(runtime.get('node'))}; Deno={bool(runtime.get('deno'))}.", recommendation="A imagem precisa oferecer Node 22+ ou Deno 2.6+."))

    ejs_ok = importlib.util.find_spec("yt_dlp_ejs") is not None
    checks.append(_check("EJS challenge solver", ejs_ok, "yt-dlp-ejs disponível." if ejs_ok else "yt-dlp-ejs não encontrado.", recommendation="Instale yt-dlp com o grupo default e faça rebuild."))

    pot_configured = bool(settings.ytdlp_pot_provider_url)
    pot_alive = _pot_provider_alive() if pot_configured else False
    checks.append(_check("PO Token Provider", pot_alive, "Provider respondendo." if pot_alive else "Provider não respondeu." if pot_configured else "Provider não configurado.", required=pot_configured, recommendation="Verifique o processo pot-provider/Supervisor ou refaça o deploy."))

    connected = db.query(YouTubeConnection).filter(YouTubeConnection.token_json.isnot(None)).all()
    oauth_valid = 0
    oauth_invalid = 0
    for connection in connected:
        try:
            status = get_connection_status(db, connection.user_id)
            if status.get("connected"):
                oauth_valid += 1
            else:
                oauth_invalid += 1
        except Exception:
            oauth_invalid += 1
    checks.append(_check(
        "Perfis YouTube",
        oauth_invalid == 0,
        f"{oauth_valid} conexão(ões) válidas; {oauth_invalid} inválida(s).",
        required=False,
        recommendation="Reconecte somente os perfis marcados como inválidos usando Escolher outra conta YouTube.",
    ))

    download = validate_download_session()
    if download.get("ok"):
        download_detail = f"Acesso validado por {download.get('strategy')} em {download.get('attempts')} tentativa(s)."
        download_recommendation = ""
    else:
        download_detail = str(download.get("error") or "Download recusado.")
        if download.get("bot_blocked"):
            download_recommendation = (
                "O código já tentou PO Token, múltiplos clientes, Deno/Node, impersonação e modo sem cookies. "
                "Se continuar bloqueado, o IP de saída da VPS precisa de proxy residencial/estático persistente."
            )
        else:
            download_recommendation = "Revise o log do teste e a configuração de rede/yt-dlp."
    checks.append(_check("Download real do YouTube", bool(download.get("ok")), download_detail, recommendation=download_recommendation))

    now = datetime.now(timezone.utc)
    stuck_jobs = 0
    for job in db.query(Job).filter(Job.status.in_(ACTIVE_JOB_STATES)).all():
        updated = job.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if (now - updated).total_seconds() > 3600:
            stuck_jobs += 1
    checks.append(_check(
        "Jobs em processamento",
        stuck_jobs == 0,
        "Nenhum job travado há mais de 60 minutos." if stuck_jobs == 0 else f"{stuck_jobs} job(s) sem atualização há mais de 60 minutos.",
        required=False,
        recommendation="Revise esses jobs antes de reenfileirar para evitar processamento duplicado.",
    ))

    required_checks = [item for item in checks if item["required"]]
    overall_ok = all(item["ok"] for item in required_checks)
    return {
        "ok": overall_ok,
        "auto_fix": auto_fix,
        "fixes_applied": fixes_applied,
        "checks": checks,
        "download": download,
        "summary": "Todos os componentes obrigatórios passaram." if overall_ok else "Há componentes obrigatórios que precisam de atenção.",
    }
