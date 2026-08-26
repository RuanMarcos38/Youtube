import importlib.util
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import urlopen

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Job, YouTubeConnection
from .download_probe import read_download_probe
from .downloader import js_runtime_status
from .runtime_download_auth import COOKIE_OVERRIDE_FILE, PROXY_OVERRIDE_FILE
from .youtube_oauth import get_connection_status, oauth_configured


ACTIVE_JOB_STATES = {
    "queued",
    "preparing",
    "checking_ffmpeg",
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


def _cleanup_safe_runtime_artifacts() -> list[str]:
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

    for path in (settings.data_path, settings.data_path / "users", settings.sqlite_file.parent):
        try:
            if not path.exists():
                path.mkdir(parents=True, exist_ok=True)
                fixes.append(f"Diretório criado: {path.name or 'data'}.")
        except Exception:
            pass

    try:
        for temp in settings.data_path.glob("users/*/editor-projects/*/*.tmp"):
            try:
                if temp.is_file() and temp.stat().st_size == 0:
                    temp.unlink(missing_ok=True)
                    fixes.append("Arquivo temporário vazio do editor removido.")
            except Exception:
                continue
    except Exception:
        pass
    return fixes


def _check(name: str, ok: bool, detail: str, *, required: bool = True, recommendation: str = "") -> dict:
    return {
        "name": name,
        "ok": bool(ok),
        "required": required,
        "detail": str(detail)[:1800],
        "recommendation": recommendation if not ok else "",
    }


def _safe_check(checks: list[dict], name: str, runner, *, required: bool = True, recommendation: str = "") -> None:
    try:
        ok, detail = runner()
        checks.append(_check(name, bool(ok), str(detail), required=required, recommendation=recommendation))
    except Exception as exc:
        checks.append(_check(name, False, f"Falha durante o teste: {exc}", required=required, recommendation=recommendation or "Revisar logs do serviço shortsia."))


def _probe_age_seconds(probe: dict) -> float | None:
    raw = probe.get("checked_at")
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - value).total_seconds())
    except Exception:
        return None


def _download_check_from_probe() -> tuple[dict, dict]:
    probe = read_download_probe()
    if not probe:
        download = {
            "ok": False,
            "mode": "pending",
            "strategy": None,
            "attempts": 0,
            "bot_blocked": False,
            "error": "O worker ainda não gravou o primeiro probe real do YouTube.",
        }
        return download, _check(
            "Download real do YouTube",
            False,
            download["error"],
            required=False,
            recommendation="Aguarde o probe assíncrono do worker. O diagnóstico não executa downloads longos dentro da requisição HTTP.",
        )

    age = _probe_age_seconds(probe)
    stale = age is not None and age > 30 * 60
    download = dict(probe)
    ok = bool(probe.get("ok")) and not stale
    if ok:
        detail = f"Último probe real aprovado por {probe.get('strategy') or probe.get('mode') or 'rota disponível'}."
        recommendation = ""
    else:
        detail = str(probe.get("error") or "Último probe real não foi aprovado.")
        if stale:
            detail = f"Probe do YouTube está desatualizado ({int((age or 0) / 60)} min). {detail}"
        if probe.get("bot_blocked"):
            recommendation = "O YouTube está recusando a sessão/IP de saída. Renove a sessão autorizada ou configure proxy residencial/estático persistente sem alterar outras credenciais."
        else:
            recommendation = "Revisar o último probe assíncrono do worker e os logs do downloader."
    return download, _check("Download real do YouTube", ok, detail, required=False, recommendation=recommendation)


def _google_oauth_check() -> tuple[bool, str]:
    if not oauth_configured():
        return False, "Cliente OAuth ausente."

    return True, (
        "Cliente OAuth configurado. Redirect ativo: "
        f"{settings.youtube_oauth_redirect_uri}. "
        "Se uma conta Google externa receber 403 access_denied, o app OAuth ainda "
        "está em modo de teste/não verificado para essa conta; adicione o e-mail em "
        "Test users no Google Cloud Console ou publique/verifique o app."
    )


def _editor_projects_health() -> tuple[bool, str]:
    users_root = settings.data_path / "users"
    if not users_root.exists():
        return True, "Nenhum workspace de editor criado ainda; estrutura disponível."
    total = 0
    invalid = 0
    failed = 0
    rendering = 0
    for path in users_root.glob("*/editor-projects/*/project.json"):
        if total >= 250:
            break
        total += 1
        try:
            project = json.loads(path.read_text(encoding="utf-8"))
            status = str(project.get("status") or "")
            if status == "failed":
                failed += 1
            if status in {"queued", "analyzing", "transcribing", "ai_editing", "rendering", "export_queued", "exporting"}:
                rendering += 1
            if not project.get("id") or not project.get("source_filename"):
                invalid += 1
        except Exception:
            invalid += 1
    ok = invalid == 0
    return ok, f"{total} projeto(s) verificados; {failed} com falha histórica; {rendering} em processamento; {invalid} arquivo(s) inválido(s)."


def _storage_health() -> tuple[bool, str]:
    settings.data_path.mkdir(parents=True, exist_ok=True)
    test_file = settings.data_path / ".diagnostics-write-test"
    test_file.write_text("ok", encoding="utf-8")
    test_file.unlink(missing_ok=True)
    usage = shutil.disk_usage(settings.data_path)
    free_gb = usage.free / (1024 ** 3)
    ok = free_gb >= 1.0
    return ok, f"Armazenamento gravável; {free_gb:.1f} GB livres."


def run_self_test(db: Session, *, auto_fix: bool = True) -> dict:
    fixes_applied = _cleanup_safe_runtime_artifacts() if auto_fix else []
    checks: list[dict] = []

    def db_test():
        db.execute(text("SELECT 1"))
        return True, "Conexão SQL respondendo."

    _safe_check(checks, "Banco de dados", db_test, recommendation="Revisar DATABASE_URL/SQLite do serviço shortsia.")
    _safe_check(checks, "Worker", lambda: (_worker_alive(), "Heartbeat ativo." if _worker_alive() else "Heartbeat do worker não foi encontrado ou está atrasado."), recommendation="O Supervisor deve reiniciar o worker; verifique os logs se continuar inativo.")
    _safe_check(checks, "FFmpeg", lambda: (bool(shutil.which(settings.ffmpeg_binary)), "FFmpeg disponível." if shutil.which(settings.ffmpeg_binary) else "FFmpeg não encontrado."), recommendation="Reconstruir a imagem Docker oficial do ShortsFlow.")
    _safe_check(checks, "FFprobe", lambda: (bool(shutil.which(settings.ffprobe_binary)), "FFprobe disponível." if shutil.which(settings.ffprobe_binary) else "FFprobe não encontrado."), recommendation="Reconstruir a imagem Docker oficial do ShortsFlow.")
    _safe_check(checks, "Armazenamento", _storage_health, recommendation="Liberar espaço em disco antes de novos renders ou uploads.")

    checks.append(_check("OpenAI", bool(settings.openai_api_key), "API key configurada." if settings.openai_api_key else "API key ausente.", recommendation="Configure OPENAI_API_KEY apenas no ambiente seguro do EasyPanel."))
    checks.append(_check("YouTube Data API", bool(settings.youtube_api_key), "API key configurada." if settings.youtube_api_key else "API key ausente.", required=False, recommendation="Configure YOUTUBE_API_KEY no EasyPanel para busca de tendências."))
    _safe_check(
        checks,
        "Google OAuth",
        _google_oauth_check,
        required=False,
        recommendation="Configure Client ID/Secret e mantenha o app Google em Produção ou adicione o e-mail em Test users.",
    )

    runtime = js_runtime_status()
    js_ok = bool(runtime.get("node") or runtime.get("deno"))
    checks.append(_check("Runtime JavaScript yt-dlp", js_ok, f"Node={bool(runtime.get('node'))}; Deno={bool(runtime.get('deno'))}.", required=False, recommendation="A imagem precisa oferecer Node 22+ ou Deno 2.6+."))

    ejs_ok = importlib.util.find_spec("yt_dlp_ejs") is not None
    checks.append(_check("EJS challenge solver", ejs_ok, "yt-dlp-ejs disponível." if ejs_ok else "yt-dlp-ejs não encontrado.", required=False, recommendation="Instale yt-dlp com o grupo default e faça rebuild."))

    pot_configured = bool(settings.ytdlp_pot_provider_url)
    pot_alive = _pot_provider_alive() if pot_configured else False
    checks.append(_check("PO Token Provider", pot_alive if pot_configured else True, "Provider respondendo." if pot_alive else "Provider não respondeu." if pot_configured else "Provider opcional não configurado.", required=False, recommendation="Verifique o processo pot-provider/Supervisor ou refaça o deploy."))

    _safe_check(
        checks,
        "Editor IA profissional",
        lambda: (
            importlib.util.find_spec("app.services.editor_ai_pro") is not None and importlib.util.find_spec("cv2") is not None,
            "Pipeline profissional e OpenCV disponíveis." if importlib.util.find_spec("cv2") is not None else "Pipeline presente, mas OpenCV não está disponível para reenquadramento por rosto.",
        ),
        recommendation="Reconstruir a imagem para restaurar opencv-python-headless e o acabamento profissional.",
    )
    _safe_check(checks, "Projetos do Editor", _editor_projects_health, required=False, recommendation="Revisar somente os project.json inválidos; não apagar projetos válidos automaticamente.")

    try:
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
        checks.append(_check("Perfis YouTube", oauth_invalid == 0, f"{oauth_valid} conexão(ões) válidas; {oauth_invalid} inválida(s).", required=False, recommendation="Reconecte somente os perfis inválidos usando Escolher outra conta YouTube."))
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        checks.append(_check("Perfis YouTube", False, f"Não foi possível validar conexões: {exc}", required=False, recommendation="Revisar tabela de conexões/OAuth sem alterar credenciais válidas."))

    download, download_check = _download_check_from_probe()
    checks.append(download_check)

    try:
        now = datetime.now(timezone.utc)
        stuck_jobs = 0
        for job in db.query(Job).filter(Job.status.in_(ACTIVE_JOB_STATES)).all():
            updated = getattr(job, "updated_at", None)
            if updated is None:
                stuck_jobs += 1
                continue
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if (now - updated).total_seconds() > 3600:
                stuck_jobs += 1
        checks.append(_check("Jobs em processamento", stuck_jobs == 0, "Nenhum job travado há mais de 60 minutos." if stuck_jobs == 0 else f"{stuck_jobs} job(s) sem atualização há mais de 60 minutos.", required=False, recommendation="Revise esses jobs antes de reenfileirar para evitar processamento duplicado."))
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        checks.append(_check("Jobs em processamento", False, f"Falha ao verificar jobs: {exc}", required=False, recommendation="Revisar banco e worker antes de reenfileirar qualquer job."))

    required_checks = [item for item in checks if item["required"]]
    overall_ok = all(item["ok"] for item in required_checks)
    attention = sum(1 for item in checks if not item["ok"])
    return {
        "ok": overall_ok,
        "auto_fix": auto_fix,
        "fixes_applied": fixes_applied,
        "checks": checks,
        "download": download,
        "summary": "Todos os componentes obrigatórios passaram." if overall_ok else f"Há {attention} verificação(ões) que precisam de atenção.",
    }
