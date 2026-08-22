import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from .downloader import validate_download_session


PROBE_FILE = settings.data_path / "youtube_download_probe.json"


def _network_unreachable(message: str) -> bool:
    lowered = str(message or "").lower()
    return any(
        marker in lowered
        for marker in (
            "network is unreachable",
            "no route to host",
            "failed to establish a new connection",
            "connection timed out",
            "connect timeout",
        )
    )


def _public_result(raw: dict) -> dict:
    ok = bool(raw.get("ok"))
    bot_blocked = bool(raw.get("bot_blocked", False))
    raw_error = str(raw.get("error") or "")
    network_unreachable = _network_unreachable(raw_error)

    # Several yt-dlp strategies may be attempted. In environments without a
    # working IPv6 route, the last strategy can end with "Network is unreachable"
    # even when earlier IPv4 attempts already reached YouTube and were challenged.
    # Prefer the actionable/root cause instead of exposing the incidental last error.
    if not ok and bot_blocked and network_unreachable:
        error = (
            "A VPS conseguiu alcançar o YouTube por uma ou mais rotas, mas o IP/sessão de saída foi recusado pelo mecanismo anti-bot. "
            "Também foi detectada uma tentativa de rede sem rota (normalmente IPv6 indisponível); essa rota secundária não é a causa principal."
        )
        failure_kind = "youtube_ip_challenge"
    elif not ok and bot_blocked:
        error = raw_error
        failure_kind = "youtube_ip_challenge"
    elif not ok and network_unreachable:
        error = raw_error
        failure_kind = "network_unreachable"
    else:
        error = raw_error
        failure_kind = "unknown" if not ok else None

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "mode": raw.get("mode"),
        "strategy": raw.get("strategy"),
        "attempts": raw.get("attempts"),
        "bot_blocked": bot_blocked,
        "network_unreachable": network_unreachable,
        "failure_kind": failure_kind,
        "error": error[:700] if not ok else "",
    }


def run_and_store_download_probe() -> dict:
    settings.data_path.mkdir(parents=True, exist_ok=True)
    try:
        raw = validate_download_session()
        result = _public_result(raw)
    except Exception as exc:
        message = str(exc)[:700]
        result = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "mode": "unknown",
            "strategy": None,
            "attempts": 0,
            "bot_blocked": False,
            "network_unreachable": _network_unreachable(message),
            "failure_kind": "network_unreachable" if _network_unreachable(message) else "unknown",
            "error": message,
        }
    tmp = PROBE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PROBE_FILE)
    return result


def read_download_probe() -> dict | None:
    if not PROBE_FILE.is_file():
        return None
    try:
        value = json.loads(PROBE_FILE.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            return None
        return value
    except Exception:
        return None
