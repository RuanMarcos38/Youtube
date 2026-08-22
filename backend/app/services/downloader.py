import base64
import binascii
import os
from pathlib import Path

from yt_dlp import YoutubeDL
from ..config import settings


COOKIE_RUNTIME_FILE = Path("/tmp/shortsflow-youtube-cookies.txt")
YTDLP_CACHE_DIR = Path("/tmp/shortsflow-yt-dlp-cache")


class DownloadError(RuntimeError):
    pass


def download_auth_configured() -> bool:
    """Return True only when a usable cookie source is actually configured."""
    if settings.ytdlp_cookies_b64.strip():
        return True
    configured_file = settings.ytdlp_cookie_file.strip()
    return bool(configured_file and Path(configured_file).is_file())


def download_proxy_configured() -> bool:
    return bool(settings.ytdlp_proxy_url.strip())


def download_access_configured() -> bool:
    return download_auth_configured() or download_proxy_configured()


def _download_auth_configured() -> bool:
    # Backwards-compatible internal alias used by older tests/callers.
    return download_auth_configured()


def _resolve_cookie_file() -> str | None:
    configured_file = settings.ytdlp_cookie_file.strip()
    if configured_file:
        path = Path(configured_file)
        if not path.is_file():
            raise DownloadError("YTDLP_COOKIE_FILE está configurado, mas o arquivo não existe no container.")
        return str(path)

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

    # yt-dlp expects the Netscape cookies.txt format. Keep the materialized
    # secret outside DATA_DIR because DATA_DIR is publicly mounted at /media.
    first_line = text.splitlines()[0] if text else ""
    if "Cookie File" not in first_line and "\t" not in text:
        raise DownloadError("O cookie informado não parece estar no formato Netscape cookies.txt.")

    COOKIE_RUNTIME_FILE.write_text(text + "\n", encoding="utf-8")
    os.chmod(COOKIE_RUNTIME_FILE, 0o600)
    return str(COOKIE_RUNTIME_FILE)


def _base_options(output_dir: Path) -> dict:
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
        "cachedir": str(YTDLP_CACHE_DIR),
        # Node 22 is already part of the runtime image. yt-dlp only enables
        # Deno by default, so Node must be explicitly enabled for EJS.
        "js_runtimes": {
            "node": {"path": settings.ytdlp_node_path or None},
        },
    }

    cookie_file = _resolve_cookie_file()
    if cookie_file:
        options["cookiefile"] = cookie_file
    if download_proxy_configured():
        options["proxy"] = settings.ytdlp_proxy_url.strip()
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
    attempts = 0
    for variant in option_variants:
        if variant is None:
            continue
        attempts += 1
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
        if bot_blocked:
            if not download_access_configured():
                raise DownloadError(
                    "O YouTube bloqueou a sessão da VPS na etapa de download. "
                    "O PO Token e o runtime JavaScript não substituem a autenticação quando o IP do servidor recebe o desafio 'not a bot'. "
                    "Configure no EasyPanel o segredo YTDLP_COOKIES_B64 com um cookies.txt autorizado em Base64, "
                    "ou YTDLP_PROXY_URL com uma saída de rede autorizada. Nenhuma credencial existente precisa ser alterada."
                )
            raise DownloadError(
                "O YouTube ainda está rejeitando a sessão de download da VPS. "
                "A autenticação/proxy está configurada, mas a sessão foi recusada ou expirou. "
                "Renove o cookies.txt autorizado ou verifique a reputação/saída do proxy."
            )

        raise DownloadError(
            f"yt-dlp falhou após {attempts} estratégias: {' | '.join(errors)}"
        )

    raise DownloadError("yt-dlp terminou sem produzir um arquivo de vídeo")
