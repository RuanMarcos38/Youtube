from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Clip, SystemSetting


KEY_PREFIX = "youtube.upload_block."
DEFAULT_BLOCK_HOURS = 24


def _key(user_id: int) -> str:
    return f"{KEY_PREFIX}{int(user_id)}"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def mark_upload_blocked(db: Session, user_id: int, message: str, *, hours: int = DEFAULT_BLOCK_HOURS) -> dict:
    now = datetime.now(timezone.utc)
    until = now + timedelta(hours=max(1, int(hours)))
    payload = {
        "blocked_at": now.isoformat(),
        "blocked_until": until.isoformat(),
        "message": str(message or "").strip(),
    }
    row = db.get(SystemSetting, _key(user_id))
    if row is None:
        row = SystemSetting(key=_key(user_id), value=json.dumps(payload, ensure_ascii=False), secret=False)
        db.add(row)
    else:
        row.value = json.dumps(payload, ensure_ascii=False)
        row.secret = False
    db.commit()
    return upload_availability(db, user_id)


def _parse(row: SystemSetting | None) -> dict | None:
    if not row or not row.value:
        return None
    try:
        data = json.loads(row.value)
        until = datetime.fromisoformat(str(data.get("blocked_until") or "").replace("Z", "+00:00"))
        blocked_at_raw = str(data.get("blocked_at") or "")
        blocked_at = datetime.fromisoformat(blocked_at_raw.replace("Z", "+00:00")) if blocked_at_raw else None
        return {
            "blocked_at": _utc(blocked_at).isoformat() if blocked_at else None,
            "blocked_until_dt": _utc(until),
            "message": str(data.get("message") or ""),
        }
    except Exception:
        return None


def _clear_expired_errors(db: Session, user_id: int) -> None:
    marker = "limite diário de uploads"
    clips = db.query(Clip).filter(Clip.user_id == user_id, Clip.status.in_(["approved", "upload_failed"])).all()
    changed = False
    for clip in clips:
        if marker in (clip.upload_error or "").lower():
            clip.upload_error = None
            if clip.status == "upload_failed":
                clip.status = "approved"
            changed = True
    if changed:
        db.commit()


def upload_availability(db: Session, user_id: int) -> dict:
    row = db.get(SystemSetting, _key(user_id))
    parsed = _parse(row)
    now = datetime.now(timezone.utc)
    if not parsed:
        return {
            "blocked": False,
            "blocked_at": None,
            "blocked_until": None,
            "seconds_remaining": 0,
            "message": "",
        }

    until = parsed["blocked_until_dt"]
    if until <= now:
        if row:
            db.delete(row)
            db.commit()
        _clear_expired_errors(db, user_id)
        return {
            "blocked": False,
            "blocked_at": parsed["blocked_at"],
            "blocked_until": until.isoformat(),
            "seconds_remaining": 0,
            "message": "A janela estimada de 24 horas terminou. O envio pode ser testado novamente.",
        }

    return {
        "blocked": True,
        "blocked_at": parsed["blocked_at"],
        "blocked_until": until.isoformat(),
        "seconds_remaining": max(1, int((until - now).total_seconds())),
        "message": parsed["message"] or "O YouTube bloqueou temporariamente novos uploads deste canal.",
    }


def ensure_upload_available(db: Session, user_id: int) -> tuple[bool, dict]:
    current = upload_availability(db, user_id)
    return (not current["blocked"]), current
