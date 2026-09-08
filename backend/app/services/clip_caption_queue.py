from __future__ import annotations

from datetime import datetime, timezone
import json

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Clip, SystemSetting
from .automatic_mode import AUTO_JOB_PREFIX
from .automatic_mode_guard import _force_render_without_caption, _mark_clip_clean

CAPTION_REMOVE_PREFIX = "clip_caption_remove:"
MAX_CAPTION_REMOVE_ATTEMPTS = 3
_QUEUE_MESSAGE = "Remoção de legenda em processamento."


def _queue_key(clip_id: int) -> str:
    return f"{CAPTION_REMOVE_PREFIX}{clip_id}"


def _decode_state(value: str | None) -> dict:
    try:
        payload = json.loads(value or "{}")
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


def enqueue_caption_removal(db: Session, clip: Clip, user_id: int) -> None:
    """Queue a real clean re-render without keeping a long HTTP request open."""
    key = _queue_key(clip.id)
    row = db.get(SystemSetting, key)
    payload = {
        "clip_id": clip.id,
        "user_id": user_id,
        "status": "queued",
        "attempts": 0,
        "error": None,
        "queued_at": datetime.now(timezone.utc).isoformat(),
    }
    encoded = json.dumps(payload, ensure_ascii=False)
    if row is None:
        row = SystemSetting(key=key, value=encoded, secret=False)
        db.add(row)
    else:
        row.value = encoded
        row.secret = False
    clip.upload_error = _QUEUE_MESSAGE
    clip.updated_at = datetime.now(timezone.utc)
    db.commit()


def caption_removal_pending(db: Session, clip_id: int, user_id: int | None = None) -> bool:
    row = db.get(SystemSetting, _queue_key(clip_id))
    if row is None:
        return False
    state = _decode_state(row.value)
    if user_id is not None and str(state.get("user_id")) != str(user_id):
        return False
    return str(state.get("status") or "queued") in {"queued", "processing", "failed"}


def claim_next_caption_removal() -> int | None:
    db = SessionLocal()
    try:
        rows = (
            db.query(SystemSetting)
            .filter(SystemSetting.key.like(f"{CAPTION_REMOVE_PREFIX}%"))
            .order_by(SystemSetting.key.asc())
            .limit(200)
            .all()
        )
        for row in rows:
            state = _decode_state(row.value)
            attempts = max(0, int(state.get("attempts") or 0))
            status = str(state.get("status") or "queued")
            if status == "processing":
                # A worker restart may leave a stale processing state. Reclaim it.
                status = "queued"
            if status == "failed" and attempts >= MAX_CAPTION_REMOVE_ATTEMPTS:
                continue
            if status not in {"queued", "failed"}:
                continue
            try:
                clip_id = int(state.get("clip_id") or row.key.split(":", 1)[1])
            except (TypeError, ValueError, IndexError):
                db.delete(row)
                db.commit()
                continue
            state["status"] = "processing"
            state["started_at"] = datetime.now(timezone.utc).isoformat()
            row.value = json.dumps(state, ensure_ascii=False)
            db.commit()
            return clip_id
        return None
    finally:
        db.close()


def run_caption_removal(clip_id: int) -> None:
    db = SessionLocal()
    key = _queue_key(clip_id)
    try:
        row = db.get(SystemSetting, key)
        if row is None:
            return
        state = _decode_state(row.value)
        user_id = int(state.get("user_id") or 0)
        clip = db.query(Clip).filter(Clip.id == clip_id, Clip.user_id == user_id).first()
        if clip is None:
            db.delete(row)
            db.commit()
            return

        try:
            # Always recreate the actual video from source without the ShortsFlow
            # subtitle layer. Clearing only the database field is never accepted.
            _force_render_without_caption(clip)

            auto_marker = db.get(SystemSetting, f"{AUTO_JOB_PREFIX}{clip.job_id}")
            if auto_marker is not None and str(auto_marker.value) == str(clip.user_id):
                _mark_clip_clean(db, clip)

            if (clip.upload_error or "").startswith("Remoção de legenda") or (clip.upload_error or "").startswith("Falha ao remover legenda"):
                clip.upload_error = None
            clip.updated_at = datetime.now(timezone.utc)
            db.delete(row)
            db.commit()
        except Exception as exc:
            db.rollback()
            row = db.get(SystemSetting, key)
            clip = db.query(Clip).filter(Clip.id == clip_id, Clip.user_id == user_id).first()
            if row is None:
                return
            state = _decode_state(row.value)
            attempts = max(0, int(state.get("attempts") or 0)) + 1
            state["attempts"] = attempts
            state["status"] = "failed" if attempts >= MAX_CAPTION_REMOVE_ATTEMPTS else "queued"
            state["error"] = str(exc)[:1200]
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            row.value = json.dumps(state, ensure_ascii=False)
            if clip is not None:
                clip.upload_error = (
                    f"Falha ao remover legenda ({attempts}/{MAX_CAPTION_REMOVE_ATTEMPTS}). "
                    "O vídeo permanece bloqueado para publicação até ficar limpo."
                )
                clip.updated_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()
