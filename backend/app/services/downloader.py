import base64
import binascii
import hashlib
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from yt_dlp import YoutubeDL
from ..config import settings
from .runtime_download_auth import cookie_override_file, effective_proxy_url


COOKIE_RUNTIME_FILE = Path("/tmp/shortsflow-youtube-cookies.txt")
YTDLP_CACHE_DIR = Path("/tmp/shortsflow-yt-dlp-cache")
ProgressHook = Callable[[dict], None]
TEST_VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"


class DownloadError(RuntimeError):
    pass


def download_auth_configured() -> bool:
    """Return True only when a usable cookie source is actually configured."""
    if cookie_override_file() is not None:
        return True
    if settings.ytdlp_cookies_b64.strip():
        return True
    configured_file = settings.ytdlp_cookie_file.strip()
    return bool(configured_file and Path(configured_file).is_file())


def download_proxy_configured() -> bool:
    return bool(effective_proxy_url())


def download_access_configured() -> bool:
    return download_auth_configured() or download_proxy_configured()


def _download_auth_configured() -> bool:
    return download_auth_configured()


def _runtime_cookie_file(output_dir: Path | None = None) -> Path:
    if output_dir is None:
        return COOKIE_RUNTIME_FILE
    digest = hashlib.sha256(str(output_dir.resolve()).encode("utf-8")).hexdigest()[:12]
    return COOKIE_RUNTIME_FILE.with_name(f"{COOKIE_RUNTIME_FILE.stem}-{digest}{COOKIE_RUNTIME_FILE.suffix}")


def _copy_cookie_text(text: str, target: Path) -> str:
    target.write_text(text.rstrip() + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    return str(target)


def _resolve_cookie_file(runtime_file: Path | None = None) -> str | None:
    target = runtime_file or COOKIE_RUNTIME_FILE

    override = cookie_override_file()
    if override is not None:
        try:
            return _copy_cookie_text(override.read_text(encoding="utf-8"), target)
        except Exception as exc:
            raise DownloadError("O cookie renovado pelo administrador não pôde ser lido.") from exc

    configured_file = settings.ytdlp_cookie_file.strip()
    if configured_file:
        path = Path(configured_file)
        if not path.is_file():
            raise DownloadError("YTDLP_COOKIE_FILE está configurado, mas o arquivo não existe no container.")
        try:
            return _copy_cookie_text(path.read_text(encoding="utf-8"), target)
        except Exception as exc:
            raise DownloadError("YTDLP_COOKIE_FILE existe, mas não pôde ser lido.") from exc

    encoded = "".join(settings.ytdlp_cookies_b64.split())
    if not encoded:
        return None

    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DownloadError("YTDLP_COOKIES_B64 não contém um cookies.txt válido em Base64.") from exc

    if not raw or len(raw) > 2_000_000:
        raise DownloadError("YTDLP_COOKIES_B64 está vazio ou excede o tamanho permitido.")

    try:
        text = raw.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise DownloadError("YTDLP_COOKIES_B64 precisa representar um arquivo cookies.txt UTF-8.") from exc

    first_line = text.splitlines()[0] if text else ""
    if "Cookie File" not in first_line and "\t" not in text:
        raise DownloadError("O cookie informado não parece estar no formato Netscape cookies.txt.")

    return _copy_cookie_text(text, target)


def _base_options(
    output_dir: Path,
    progress_hook: ProgressHook | None = None,
    *,
    include_cookies: bool = True,
) -> dict:
    YTDLP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
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
        "extractor_retries": 3,
        "file_access_retries": 1,
        "concurrent_fragment_downloads": 4,
        "cachedir": str(YTDLP_CACHE_DIR),
        "js_runtimes": {
            "node": {"path": settings.ytdlp_node_path or None},
        },
    }

    if progress_hook is not None:
        def safe_progress_hook(event: dict) -> None:
            try:
                progress_hook(event)
            except Exception:
                pass

        options["progress_hooks"] = [safe_progress_hook]

    if include_cookies:
        cookie_file = _resolve_cookie_file(_runtime_cookie_file(output_dir))
        if cookie_file:
            options["cookiefile"] = cookie_file

    proxy_url = effective_proxy_url()
    if proxy_url:
        options["proxy"] = proxy_url
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


def _client_args(player_client: str) -> dict:
    return {
        "extractor_args": {
            "youtube": {
                "player_client": [player_client],
            }
        }
    }


def _strategy_variants() -> list[tuple[str, dict, bool]]:
    """Return download strategies in order.

    Rejected account cookies can make every authenticated player client return
    LOGIN_REQUIRED. For public videos, retrying without those cookies can still
    work (especially with PO-token/client rotation). This also prevents one
    stale browser session from taking the whole SaaS offline.
    """
    strategies: list[tuple[str, dict, bool]] = []

    if download_auth_configured():
        authenticated = [
            ("auth:default", {}),
            ("auth:web_safari+pot", _pot_provider_args("web_safari")),
            ("auth:mweb+pot", _pot_provider_args("mweb")),
            ("auth:web_embedded", _client_args("web_embedded")),
        ]
        for name, variant in authenticated:
            if variant is not None:
                strategies.append((name, variant, True))

    guest = [
        ("guest:android_vr", _client_args("android_vr")),
        ("guest:tv_downgraded", _client_args("tv_downgraded")),
        ("guest:web_embedded", _client_args("web_embedded")),
        ("guest:mweb+pot", _pot_provider_args("mweb")),
        ("guest:web_safari+pot", _pot_provider_args("web_safari")),
        ("guest:default", {}),
    ]
    for name, variant in guest:
        if variant is not None:
            strategies.append((name, variant, False))

    return strategies


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


def validate_download_session(url: str = TEST_VIDEO_URL) -> dict:
    """Validate the current VPS egress using the same fallback chain as real jobs."""
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="shortsflow-ytdlp-check-") as tmp:
        output_dir = Path(tmp)
        for strategy, variant, include_cookies in _strategy_variants():
            options = _base_options(output_dir, include_cookies=include_cookies)
            options.update({
                "skip_download": True,
                "simulate": True,
                "quiet": True,
                "no_warnings": True,
                "extract_flat": False,
            })
            options.update(variant)
            try:
                with YoutubeDL(options) as ydl:
                    info = ydl.extract_info(url, download=False)
                return {
                    "ok": True,
                    "video_id": (info or {}).get("id"),
                    "title": (info or {}).get("title"),
                    "mode": "cookies+proxy" if include_cookies and download_proxy_configured() else "cookies" if include_cookies else "proxy" if download_proxy_configured() else "guest-fallback",
                    "strategy": strategy,
                }
            except Exception as exc:
                message = _compact_error(str(exc))
                if message and message not in errors:
                    errors.append(message)

    message = errors[-1] if errors else "Sessão de download indisponível."
    bot_blocked = any("Sign in to confirm" in item or "not a bot" in item.lower() for item in errors)
    return {
        "ok": False,
        "error": message,
        "bot_blocked": bot_blocked,
        "mode": "cookies+proxy" if download_auth_configured() and download_proxy_configured() else "cookies" if download_auth_configured() else "proxy" if download_proxy_configured() else "guest",
        "attempts": len(_strategy_variants()),
    }


def download_video(url: str, output_dir: Path, progress_hook: ProgressHook | None = None) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    attempts = 0
    for strategy, variant, include_cookies in _strategy_variants():
        attempts += 1
        options = _base_options(output_dir, progress_hook=progress_hook, include_cookies=include_cookies)
        options.update(variant)
        try:
            video_path = _download_with_options(url, output_dir, options)
            if video_path:
                return video_path
        except Exception as exc:
            error = _compact_error(str(exc))
            if error:
                tagged = f"{strategy}: {error}"
                if tagged not in errors:
                    errors.append(tagged)

    if errors:
        bot_blocked = any(
            "Sign in to confirm you're not a bot" in error
            or "Sign in to confirm you’re not a bot" in error
            or "not a bot" in error.lower()
            for error in errors
        )
        if bot_blocked:
            if not download_access_configured():
                raise DownloadError(
                    "O YouTube bloqueou a saída da VPS. As estratégias públicas/PO Token também foram recusadas. "
                    "Configure uma sessão autorizada ou uma saída de proxy no painel Administrador > Download YouTube."
                )
            raise DownloadError(
                "O YouTube recusou os cookies e também os fallbacks públicos desta VPS. "
                "Isso normalmente acontece quando os cookies foram obtidos em outro IP e o datacenter foi desafiado. "
                "Renove a sessão e teste pelo painel Administrador > Download YouTube; se a recusa persistir, "
                "use um proxy residencial/estático para manter o mesmo IP da sessão."
            )

        raise DownloadError(
            f"yt-dlp falhou após {attempts} estratégias: {' | '.join(errors)}"
        )

    raise DownloadError("yt-dlp terminou sem produzir um arquivo de vídeo")
