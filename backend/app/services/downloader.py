import base64
import binascii
import hashlib
import os
import shutil
import socket
import sys
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
    return bool(download_auth_configured() or download_proxy_configured() or settings.ytdlp_pot_provider_url.strip())


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


def _runtime_binary(name: str) -> str | None:
    configured = shutil.which(name)
    if configured:
        return configured
    candidate = Path(sys.executable).with_name(name)
    if candidate.is_file():
        return str(candidate)
    return None


def js_runtime_status() -> dict[str, str | bool]:
    node_path = settings.ytdlp_node_path.strip() or _runtime_binary("node") or ""
    deno_path = _runtime_binary("deno") or ""
    return {"node": bool(node_path), "node_path": node_path, "deno": bool(deno_path), "deno_path": deno_path}


def _js_runtimes() -> dict:
    status = js_runtime_status()
    runtimes: dict = {}
    if status["deno"]:
        runtimes["deno"] = {"path": str(status["deno_path"])}
    if status["node"]:
        runtimes["node"] = {"path": str(status["node_path"])}
    return runtimes


def _base_options(output_dir: Path, progress_hook: ProgressHook | None = None, *, include_cookies: bool = True) -> dict:
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
        "socket_timeout": 35,
        "retries": 5,
        "fragment_retries": 5,
        "extractor_retries": 4,
        "file_access_retries": 2,
        "concurrent_fragment_downloads": 2,
        "sleep_interval_requests": 1,
        "cachedir": str(YTDLP_CACHE_DIR),
        "js_runtimes": _js_runtimes(),
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


def _pot_provider_args(player_client: str = "mweb", *, skip_webpage: bool = False) -> dict | None:
    if not settings.ytdlp_pot_provider_url:
        return None
    youtube_args: dict[str, list[str]] = {"player_client": [player_client], "fetch_pot": ["always"]}
    if skip_webpage:
        youtube_args["player_skip"] = ["webpage", "configs"]
    return {"extractor_args": {"youtube": youtube_args, "youtubepot-bgutilhttp": {"base_url": [settings.ytdlp_pot_provider_url]}}}


def _client_args(player_client: str, *, skip_webpage: bool = False) -> dict:
    youtube_args: dict[str, list[str]] = {"player_client": [player_client]}
    if skip_webpage:
        youtube_args["player_skip"] = ["webpage", "configs"]
    return {"extractor_args": {"youtube": youtube_args}}


def _hls_client_args(player_client: str = "web_safari", *, skip_webpage: bool = False) -> dict:
    variant = _client_args(player_client, skip_webpage=skip_webpage)
    variant["format"] = "best[protocol*=m3u8][height<=1080]/best[height<=1080]/best"
    return variant


def _impersonated_client_args(player_client: str, *, skip_webpage: bool = False) -> dict:
    variant = _client_args(player_client, skip_webpage=skip_webpage)
    variant["impersonate"] = "chrome"
    return variant


def _ipv6_variant(variant: dict) -> dict:
    copy = dict(variant)
    copy["source_address"] = "::"
    return copy


def _strategy_variants() -> list[tuple[str, dict, bool]]:
    strategies: list[tuple[str, dict, bool]] = []
    if download_auth_configured():
        authenticated = [
            ("auth:mweb+pot:skip-webpage", _pot_provider_args("mweb", skip_webpage=True)),
            ("auth:mweb+pot", _pot_provider_args("mweb")),
            ("auth:web_safari+pot", _pot_provider_args("web_safari")),
            ("auth:web_safari:hls", _hls_client_args("web_safari", skip_webpage=True)),
            ("auth:tv_embedded", _client_args("tv_embedded", skip_webpage=True)),
            ("auth:web_embedded", _client_args("web_embedded", skip_webpage=True)),
            ("auth:default", {}),
        ]
        for name, variant in authenticated:
            if variant is not None:
                strategies.append((name, variant, True))
    guest = [
        ("guest:mweb+pot:skip-webpage", _pot_provider_args("mweb", skip_webpage=True)),
        ("guest:mweb+pot", _pot_provider_args("mweb")),
        ("guest:web_safari:hls:skip-webpage", _hls_client_args("web_safari", skip_webpage=True)),
        ("guest:web_safari+pot", _pot_provider_args("web_safari")),
        ("guest:web_safari", _client_args("web_safari")),
        ("guest:tv", _client_args("tv", skip_webpage=True)),
        ("guest:tv_simply", _client_args("tv_simply", skip_webpage=True)),
        ("guest:android_vr", _client_args("android_vr", skip_webpage=True)),
        ("guest:ios", _client_args("ios", skip_webpage=True)),
        ("guest:web_embedded", _client_args("web_embedded", skip_webpage=True)),
        ("guest:chrome:mweb+pot", None if not settings.ytdlp_pot_provider_url else {**_pot_provider_args("mweb", skip_webpage=True), "impersonate": "chrome"}),
        ("guest:chrome:web_safari", _impersonated_client_args("web_safari", skip_webpage=True)),
    ]
    if socket.has_ipv6:
        ipv6_candidates = [
            ("guest:ipv6:mweb+pot", _pot_provider_args("mweb", skip_webpage=True)),
            ("guest:ipv6:web_safari:hls", _hls_client_args("web_safari", skip_webpage=True)),
            ("guest:ipv6:web_safari", _client_args("web_safari", skip_webpage=True)),
        ]
        for name, variant in ipv6_candidates:
            if variant is not None:
                guest.insert(0, (name, _ipv6_variant(variant)))
    guest.append(("guest:default", {}))
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
    return text[:497] + "..." if len(text) > 500 else text


def _is_bot_block(message: str) -> bool:
    lowered = message.lower()
    return "sign in to confirm" in lowered or "not a bot" in lowered or "login_required" in lowered or "http error 403" in lowered or "forbidden" in lowered


def validate_download_session(url: str = TEST_VIDEO_URL) -> dict:
    errors: list[str] = []
    attempted: list[str] = []
    with tempfile.TemporaryDirectory(prefix="shortsflow-ytdlp-check-") as tmp:
        output_dir = Path(tmp)
        for strategy, variant, include_cookies in _strategy_variants():
            attempted.append(strategy)
            options = _base_options(output_dir, include_cookies=include_cookies)
            options.update({"skip_download": True, "simulate": True, "quiet": True, "no_warnings": True, "extract_flat": False})
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
                    "attempts": len(attempted),
                    "js_runtimes": js_runtime_status(),
                    "pot_provider": bool(settings.ytdlp_pot_provider_url),
                }
            except Exception as exc:
                message = _compact_error(str(exc))
                if message and message not in errors:
                    errors.append(message)
    message = errors[-1] if errors else "Sessão de download indisponível."
    return {
        "ok": False,
        "error": message,
        "bot_blocked": any(_is_bot_block(item) for item in errors),
        "mode": "cookies+proxy" if download_auth_configured() and download_proxy_configured() else "cookies" if download_auth_configured() else "proxy" if download_proxy_configured() else "guest",
        "attempts": len(attempted),
        "strategies": attempted,
        "js_runtimes": js_runtime_status(),
        "pot_provider": bool(settings.ytdlp_pot_provider_url),
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
        if any(_is_bot_block(error) for error in errors):
            if not download_proxy_configured():
                raise DownloadError(
                    "O YouTube recusou todas as rotas automáticas desta VPS, incluindo PO Token, clientes alternativos, web_safari/HLS, tentativas sem webpage, Deno/Node e saída IPv6 quando disponível. Isso caracteriza bloqueio de reputação da rede de saída. Para estabilidade de produção, configure no Administrador > Download YouTube um proxy residencial/estático com IP persistente. Se usar cookies, renove-os através do mesmo IP do proxy."
                )
            raise DownloadError("O YouTube recusou o IP/proxy atual mesmo após a cadeia completa de fallbacks. Valide a reputação/saída do proxy no Administrador > Download YouTube e mantenha cookies e proxy no mesmo IP.")
        raise DownloadError(f"yt-dlp falhou após {attempts} estratégias: {' | '.join(errors)}")
    raise DownloadError("yt-dlp terminou sem produzir um arquivo de vídeo")
