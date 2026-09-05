from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import SystemSetting, TikTokPost


PUBLIC_AUDIT_SETTING_PREFIX = "tiktok_public_audit_block_user_"
PUBLIC_AUDIT_BLOCK_HOURS = 6
PUBLIC_AUDIT_BLOCK_REASON = (
    "O TikTok bloqueou o Direct Post público porque o app da Content Posting API ainda não está auditado. "
    "O ShortsFlow usará o fluxo oficial de Upload para enviar o vídeo à Caixa de Entrada/Rascunhos do TikTok, "
    "onde você poderá revisar e concluir a publicação no app. Se o envio de rascunho pedir nova permissão, "
    "clique em 'Trocar conta TikTok' e autorize video.upload."
)
PRIVATE_ACCOUNT_AUDIT_BLOCK_REASON = (
    "O TikTok ainda restringe o Direct Post deste app. O ShortsFlow mantém 'Somente eu' disponível para teste e, "
    "quando necessário, usa o fluxo oficial de Upload/Rascunhos. Para publicação pública automática, conclua a auditoria do app."
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
    """Remember that Direct Post is audit-blocked so queued items can use Upload instead."""
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
    """Remove the local TikTok Direct Post audit gate."""
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
    """Keep the TikTok controls usable while routing audit-blocked Direct Posts to Upload.

    SELF_ONLY acts as the UI-safe choice while the worker uses the local audit
    marker to select TikTok's official inbox/draft Upload flow. It is not used
    to pretend that a public Direct Post succeeded.
    """
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
        adjusted["privacy_level_options"] = ["SELF_ONLY"]
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
    """Undo a batch when neither Direct Post nor the Upload fallback can proceed."""
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
        if post.status == "paused_limit" and post.id != current_post_id and not is_unaudited_error_text(post.error):
            continue
        if post.id == current_post_id:
            post.status = "failed"
            post.error = current_error or (
                "O Direct Post está bloqueado pela auditoria do TikTok e o envio para Rascunhos não pôde ser concluído. "
                "Reconecte o TikTok autorizando video.upload ou conclua a auditoria no TikTok for Developers."
            )
        else:
            post.status = "ready"
            post.error = None
        post.publish_id = None
        changed += 1
    db.commit()
    return changed
