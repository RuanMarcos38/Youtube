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


def _latest_successful_upload_at(db: Session, user_id: int, *, before: datetime | None = None) -> datetime | None:
    """Return the latest YouTube upload completed by ShortsFlow for this user.

    The daily-limit countdown must be anchored to the last successful upload,
    not to the later instant when YouTube happens to return the limit error.
    We inspect a few recent uploaded clips in Python so timezone differences in
    SQLite/Postgres do not make the query brittle.
    """
    before_utc = _utc(before) if before else datetime.now(timezone.utc)
    candidates = (
        db.query(Clip)
        .filter(
            Clip.user_id == user_id,
            Clip.youtube_video_id.isnot(None),
            Clip.status == "uploaded",
        )
        .order_by(Clip.updated_at.desc(), Clip.id.desc())
        .limit(25)
        .all()
    )
    for clip in candidates:
        if not clip.updated_at:
            continue
        uploaded_at = _utc(clip.updated_at)
        if uploaded_at <= before_utc:
            return uploaded_at
    return None


def _reference_upload_at(
    db: Session,
    user_id: int,
    *,
    detected_at: datetime,
    hours: int,
) -> datetime | None:
    latest = _latest_successful_upload_at(db, user_id, before=detected_at)
    if not latest:
        return None
    age = detected_at - latest
    if age < timedelta(0) or age > timedelta(hours=hours):
        return None
    return latest


def mark_upload_blocked(db: Session, user_id: int, message: str, *, hours: int = DEFAULT_BLOCK_HOURS) -> dict:
    detected_at = datetime.now(timezone.utc)
    block_hours = max(1, int(hours))
    reference_upload = _reference_upload_at(
        db,
        user_id,
        detected_at=detected_at,
        hours=block_hours,
    )
    anchor = reference_upload or detected_at
    until = anchor + timedelta(hours=block_hours)
    payload = {
        "blocked_at": detected_at.isoformat(),
        "reference_upload_at": reference_upload.isoformat() if reference_upload else None,
        "blocked_until": until.isoformat(),
        "block_hours": block_hours,
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
        reference_raw = str(data.get("reference_upload_at") or "")
        reference_upload = datetime.fromisoformat(reference_raw.replace("Z", "+00:00")) if reference_raw else None
        return {
            "blocked_at": _utc(blocked_at).isoformat() if blocked_at else None,
            "blocked_at_dt": _utc(blocked_at) if blocked_at else None,
            "reference_upload_at": _utc(reference_upload).isoformat() if reference_upload else None,
            "reference_upload_at_dt": _utc(reference_upload) if reference_upload else None,
            "blocked_until_dt": _utc(until),
            "block_hours": max(1, int(data.get("block_hours") or DEFAULT_BLOCK_HOURS)),
            "message": str(data.get("message") or ""),
        }
    except Exception:
        return None


def _reconcile_existing_block(db: Session, user_id: int, row: SystemSetting, parsed: dict) -> dict:
    """Repair blocks created by older versions that started the 24h clock too late.

    Existing production rows used `error_detected_at + 24h`. When there is a
    successful ShortsFlow upload shortly before that error, shorten the window
    to `last_successful_upload + 24h`. Never extend a stored block here.
    """
    if parsed.get("reference_upload_at_dt"):
        return parsed

    detected_at = parsed.get("blocked_at_dt") or datetime.now(timezone.utc)
    block_hours = int(parsed.get("block_hours") or DEFAULT_BLOCK_HOURS)
    reference_upload = _reference_upload_at(
        db,
        user_id,
        detected_at=detected_at,
        hours=block_hours,
    )
    if not reference_upload:
        return parsed

    corrected_until = reference_upload + timedelta(hours=block_hours)
    if corrected_until >= parsed["blocked_until_dt"]:
        return parsed

    payload = {
        "blocked_at": parsed.get("blocked_at"),
        "reference_upload_at": reference_upload.isoformat(),
        "blocked_until": corrected_until.isoformat(),
        "block_hours": block_hours,
        "message": parsed.get("message") or "",
    }
    row.value = json.dumps(payload, ensure_ascii=False)
    row.secret = False
    db.commit()
    return _parse(row) or parsed


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
            "reference_upload_at": None,
            "blocked_until": None,
            "seconds_remaining": 0,
            "message": "",
        }

    if row:
        parsed = _reconcile_existing_block(db, user_id, row, parsed)

    until = parsed["blocked_until_dt"]
    if until <= now:
        if row:
            db.delete(row)
            db.commit()
        _clear_expired_errors(db, user_id)
        return {
            "blocked": False,
            "blocked_at": parsed["blocked_at"],
            "reference_upload_at": parsed.get("reference_upload_at"),
            "blocked_until": until.isoformat(),
            "seconds_remaining": 0,
            "message": "A janela estimada de 24 horas terminou. O envio pode ser testado novamente.",
        }

    return {
        "blocked": True,
        "blocked_at": parsed["blocked_at"],
        "reference_upload_at": parsed.get("reference_upload_at"),
        "blocked_until": until.isoformat(),
        "seconds_remaining": max(1, int((until - now).total_seconds())),
        "message": parsed["message"] or "O YouTube bloqueou temporariamente novos uploads deste canal.",
    }


def ensure_upload_available(db: Session, user_id: int) -> tuple[bool, dict]:
    current = upload_availability(db, user_id)
    return (not current["blocked"]), current
