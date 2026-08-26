import json
from datetime import datetime, timezone

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
    network_unreachable = bool(raw.get("network_unreachable", False)) or _network_unreachable(raw_error)

    # validate_download_session keeps the actionable YouTube challenge as the
    # primary failure. Preserve aggregate network diagnostics separately so a
    # secondary route failure can never replace the real root cause in the UI.
    if not ok and bot_blocked and network_unreachable:
        error = (
            "A VPS conseguiu alcançar o YouTube por IPv4, mas o IP/sessão de saída foi recusado pelo mecanismo anti-bot. "
            "Também houve uma falha secundária de rede em alguma tentativa; ela não é a causa principal."
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
        "ip_family": raw.get("ip_family", "ipv4"),
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
            "ip_family": "ipv4",
            "bot_blocked": False,
            "network_unreachable": _network_unreachable(message),
            "failure_kind": "network_unreachable" if _network_unreachable(message) else "unknown",
            "error": message,
        }
    tmp = PROBE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    tmp.replace(PROBE_FILE)
    return result


def store_download_probe_result(raw: dict) -> dict:
    settings.data_path.mkdir(parents=True, exist_ok=True)
    result = _public_result(raw)
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
