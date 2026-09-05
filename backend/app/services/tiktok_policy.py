from sqlalchemy.orm import Session

from ..models import SystemSetting, TikTokPost


PUBLIC_AUDIT_SETTING_PREFIX = "tiktok_public_audit_block_user_"
UNAUDITED_CODE = "unaudited_client_can_only_post_to_private_accounts"
UNAUDITED_MARKERS = (
    UNAUDITED_CODE,
    "não auditado",
    "nao auditado",
)


def _setting_key(user_id: int) -> str:
    return f"{PUBLIC_AUDIT_SETTING_PREFIX}{int(user_id)}"


def is_unaudited_error_text(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and any(marker in text for marker in UNAUDITED_MARKERS)


def clear_legacy_unaudited_public_block(db: Session, *, user_id: int) -> bool:
    """Remove the old short-lived local gate for TikTok public posting."""
    key = _setting_key(user_id)
    marker = db.get(SystemSetting, key)
    if marker is None:
        return False
    db.delete(marker)
    db.commit()
    return True


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
    """Clear local-only audit state so TikTok Creator Info remains authoritative."""
    clear_legacy_unaudited_public_block(db, user_id=user_id)
    recover_legacy_unaudited_pauses(db, user_id=user_id)


def release_unaudited_public_queue(db: Session, *, user_id: int, current_post_id: int) -> int:
    """Undo a public batch after TikTok authoritatively rejects an unaudited client.

    The first failed Direct Post is enough to prove the client-level restriction. All
    queued clips are returned to a clean, retryable state instead of showing the same
    red error dozens of times. No video is silently changed to private, and public
    visibility is not hidden locally when TikTok's current Creator Info allows it.
    """
    clear_legacy_unaudited_public_block(db, user_id=user_id)
    rows = (
        db.query(TikTokPost)
        .filter(
            TikTokPost.user_id == user_id,
            TikTokPost.status.in_(["queued", "uploading", "paused_limit"]),
        )
        .all()
    )
    changed = 0
    for post in rows:
        # Keep genuine rate/cap pauses untouched. Only the current failed item,
        # active queue rows and old audit-specific pauses are released.
        if post.status == "paused_limit" and post.id != current_post_id and not is_unaudited_error_text(post.error):
            continue
        post.status = "ready"
        post.error = None
        post.publish_id = None
        changed += 1
    db.commit()
    return changed
