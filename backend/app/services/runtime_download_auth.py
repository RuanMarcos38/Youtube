import base64
import binascii
import os
from pathlib import Path
from urllib.parse import urlparse

from ..config import settings


COOKIE_OVERRIDE_FILE = settings.data_path / "youtube_download_cookies_override.txt"
PROXY_OVERRIDE_FILE = settings.data_path / "youtube_download_proxy_override.txt"


def _validated_cookie_text(encoded: str) -> str:
    compact = "".join((encoded or "").split())
    if not compact:
        raise ValueError("Informe o YTDLP_COOKIES_B64 gerado pelo Firefox.")
    try:
        raw = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("O conteúdo informado não é Base64 válido.") from exc
    if not raw or len(raw) > 2_000_000:
        raise ValueError("O cookies.txt está vazio ou excede o tamanho permitido.")
    try:
        text = raw.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("O cookies.txt precisa estar em UTF-8.") from exc
    if "youtube.com" not in text.lower():
        raise ValueError("O arquivo não contém cookies do YouTube.")
    if "Cookie File" not in (text.splitlines()[0] if text else "") and "\t" not in text:
        raise ValueError("O arquivo não parece estar no formato Netscape cookies.txt.")
    return text + "\n"


def set_cookie_override(encoded: str) -> None:
    text = _validated_cookie_text(encoded)
    COOKIE_OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    COOKIE_OVERRIDE_FILE.write_text(text, encoding="utf-8")
    os.chmod(COOKIE_OVERRIDE_FILE, 0o600)


def clear_cookie_override() -> None:
    COOKIE_OVERRIDE_FILE.unlink(missing_ok=True)


def cookie_override_file() -> Path | None:
    return COOKIE_OVERRIDE_FILE if COOKIE_OVERRIDE_FILE.is_file() and COOKIE_OVERRIDE_FILE.stat().st_size > 0 else None


def set_proxy_override(proxy_url: str) -> None:
    value = (proxy_url or "").strip()
    if not value:
        clear_proxy_override()
        return
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https", "socks5", "socks5h"} or not parsed.hostname:
        raise ValueError("Proxy inválido. Use http(s):// ou socks5(h):// com host válido.")
    PROXY_OVERRIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROXY_OVERRIDE_FILE.write_text(value, encoding="utf-8")
    os.chmod(PROXY_OVERRIDE_FILE, 0o600)


def clear_proxy_override() -> None:
    PROXY_OVERRIDE_FILE.unlink(missing_ok=True)


def proxy_override_url() -> str:
    if not PROXY_OVERRIDE_FILE.is_file():
        return ""
    try:
        return PROXY_OVERRIDE_FILE.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def effective_proxy_url() -> str:
    return proxy_override_url() or settings.ytdlp_proxy_url.strip()


def status_payload() -> dict:
    return {
        "cookie_override": cookie_override_file() is not None,
        "cookie_environment": bool(settings.ytdlp_cookies_b64.strip() or settings.ytdlp_cookie_file.strip()),
        "proxy_override": bool(proxy_override_url()),
        "proxy_environment": bool(settings.ytdlp_proxy_url.strip()),
    }
