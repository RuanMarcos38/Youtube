import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings
from .downloader import validate_download_session


PROBE_FILE = settings.data_path / "youtube_download_probe.json"


def _public_result(raw: dict) -> dict:
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": bool(raw.get("ok")),
        "mode": raw.get("mode"),
        "strategy": raw.get("strategy"),
        "attempts": raw.get("attempts"),
        "bot_blocked": bool(raw.get("bot_blocked", False)),
        "error": str(raw.get("error") or "")[:700] if not raw.get("ok") else "",
    }


def run_and_store_download_probe() -> dict:
    settings.data_path.mkdir(parents=True, exist_ok=True)
    try:
        raw = validate_download_session()
        result = _public_result(raw)
    except Exception as exc:
        result = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "mode": "unknown",
            "strategy": None,
            "attempts": 0,
            "bot_blocked": False,
            "error": str(exc)[:700],
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
