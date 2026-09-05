from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import SystemSetting, TikTokPost


PUBLIC_AUDIT_SETTING_PREFIX = "tiktok_public_audit_block_user_"
PUBLIC_AUDIT_BLOCK_HOURS = 6
PUBLIC_AUDIT_BLOCK_REASON = (
    "O TikTok recusou o Direct Post porque o app da Content Posting API ainda não está auditado. "
    "Clientes não auditados só conseguem testar Direct Post em contas TikTok privadas; nesta conta pública, "
    "até 'Somente eu' é recusado pelo TikTok. Conclua a auditoria do app no TikTok for Developers ou torne a conta TikTok privada para teste."
)
PRIVATE_ACCOUNT_AUDIT_BLOCK_REASON = (
    "O TikTok recusou publicação pública porque o app da Content Posting API ainda não está auditado. "
    "Nesta conta TikTok privada, teste somente com 'Somente eu'. Para publicar publicamente, conclua a auditoria do app no TikTok for Developers."
)
UNAUDITED_CODE = "unaudited_client_can_only_post_to_private_accounts"
UNAUDITED_MARKERS = (
    UNAUDITED_CODE,
    "não auditado",
    "nao auditado",
)


def _setting_key(user_id: int) -> str:
    return f"{PUBLIC_AUDIT_SETTING_PREFIX}{int(user_id)}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_unaudited_error_text(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and any(marker in text for marker in UNAUDITED_MARKERS)


def mark_unaudited_public_block(db: Session, *, user_id: int, commit: bool = True) -> datetime:
    """Temporarily hide public posting after TikTok proves the client is unaudited."""
    blocked_until = _utcnow() + timedelta(hours=PUBLIC_AUDIT_BLOCK_HOURS)
    key = _setting_key(user_id)
    marker = db.get(SystemSetting, key)
    if marker is None:
        marker = SystemSetting(key=key, value=blocked_until.isoformat(), secret=False)
        db.add(marker)
    else:
        marker.value = blocked_until.isoformat()
        marker.secret = False
    if commit:
        db.commit()
    return blocked_until


def clear_unaudited_public_block(db: Session, *, user_id: int, commit: bool = True) -> bool:
    """Remove the local TikTok public-posting audit gate."""
    key = _setting_key(user_id)
    marker = db.get(SystemSetting, key)
    if marker is None:
        return False
    db.delete(marker)
    if commit:
        db.commit()
    return True


def unaudited_public_block_active(db: Session, *, user_id: int) -> bool:
    key = _setting_key(user_id)
    marker = db.get(SystemSetting, key)
    if marker is None:
        return False
    blocked_until = _parse_iso(marker.value)
    if blocked_until is None or blocked_until <= _utcnow():
        db.delete(marker)
        db.commit()
        return False
    return True


def sync_unaudited_public_block_from_recent_failure(db: Session, *, user_id: int, commit: bool = True) -> bool:
    """Restore the Direct Post audit gate from a recent unaudited failure."""
    cutoff = _utcnow() - timedelta(hours=PUBLIC_AUDIT_BLOCK_HOURS)
    rows = (
        db.query(TikTokPost)
        .filter(
            TikTokPost.user_id == user_id,
            TikTokPost.status == "failed",
            TikTokPost.error.is_not(None),
        )
        .order_by(TikTokPost.updated_at.desc(), TikTokPost.id.desc())
        .limit(20)
        .all()
    )
    for post in rows:
        if _as_utc(post.updated_at) < cutoff:
            continue
        if not is_unaudited_error_text(post.error):
            continue
        mark_unaudited_public_block(db, user_id=user_id, commit=commit)
        return True
    return False


def apply_unaudited_public_block(db: Session, *, user_id: int, creator: dict) -> dict:
    """Return Creator Info adjusted after TikTok proves the client is unaudited."""
    active = unaudited_public_block_active(db, user_id=user_id)
    if not active:
        active = sync_unaudited_public_block_from_recent_failure(db, user_id=user_id)
    if not active:
        return creator
    options = [str(value) for value in (creator.get("privacy_level_options") or []) if str(value).strip()]
    public_account = "PUBLIC_TO_EVERYONE" in options
    adjusted = dict(creator)
    adjusted["public_posting_blocked"] = True
    if public_account:
        adjusted["privacy_level_options"] = []
        adjusted["public_posting_block_reason"] = PUBLIC_AUDIT_BLOCK_REASON
    else:
        adjusted["privacy_level_options"] = [value for value in options if value == "SELF_ONLY"]
        adjusted["public_posting_block_reason"] = PRIVATE_ACCOUNT_AUDIT_BLOCK_REASON
    return adjusted


def recover_legacy_unaudited_pauses(db: Session, *, user_id: int | None = None) -> int:
    """Clean the old behavior that copied one audit error to every queued clip."""
    query = db.query(TikTokPost).filter(
        TikTokPost.status == "paused_limit",
        TikTokPost.error.is_not(None),
    )
    if user_id is not None:
        query = query.filter(TikTokPost.user_id == int(user_id))
    rows = query.order_by(TikTokPost.user_id.asc(), TikTokPost.id.asc()).all()

    changed = 0
    for post in rows:
        if not is_unaudited_error_text(post.error):
            continue
        post.status = "ready"
        post.error = None
        post.publish_id = None
        changed += 1

    if changed:
        db.commit()
    return changed


def clear_legacy_unaudited_state(db: Session, *, user_id: int) -> None:
    """Recover old per-clip audit pauses without clearing the current public gate."""
    recover_legacy_unaudited_pauses(db, user_id=user_id)


def release_unaudited_public_queue(
    db: Session,
    *,
    user_id: int,
    current_post_id: int,
    current_error: str | None = None,
) -> int:
    """Undo a Direct Post batch after TikTok authoritatively rejects an unaudited client.

    The first failed Direct Post is enough to prove the client/account-level
    restriction. Pending clips are returned to a clean, retryable state instead
    of showing the same red error dozens of times. The clip that proved the
    rejection keeps a visible error so the failed attempt is never silent.
    """
    mark_unaudited_public_block(db, user_id=user_id, commit=False)
    rows = (
        db.query(TikTokPost)
        .filter(
            TikTokPost.user_id == user_id,
            or_(
                TikTokPost.id == current_post_id,
                TikTokPost.status.in_(["queued", "uploading", "paused_limit"]),
                TikTokPost.status.in_(["processing", "submitted"]) & TikTokPost.publish_id.is_(None),
            ),
        )
        .all()
    )
    changed = 0
    for post in rows:
        # Keep genuine rate/cap pauses untouched. Only the current failed item,
        # active queue rows and old audit-specific pauses are released.
        if post.status == "paused_limit" and post.id != current_post_id and not is_unaudited_error_text(post.error):
            continue
        if post.id == current_post_id:
            post.status = "failed"
            post.error = current_error or (
                "O TikTok recusou a publicação pública porque o app da Content Posting API ainda "
                "não está auditado para posts públicos. Use 'Somente eu' para testar ou conclua "
                "a auditoria no TikTok for Developers."
            )
        else:
            post.status = "ready"
            post.error = None
        post.publish_id = None
        changed += 1
    db.commit()
    return changed
