from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from ..models import SystemSetting, TikTokPost


PUBLIC_AUDIT_SETTING_PREFIX = "tiktok_public_audit_block_user_"
PUBLIC_AUDIT_BLOCK_HOURS = 6
PUBLIC_AUDIT_BLOCK_REASON = (
    "O TikTok confirmou que este app da Content Posting API ainda não está auditado. "
    "Enquanto o app estiver não auditado, o Direct Post de teste só é permitido quando a CONTA TIKTOK também estiver PRIVADA "
    "e a privacidade do vídeo for 'Somente eu'. Sua conta foi identificada como pública. "
    "Para testar a publicação automática agora, deixe a conta TikTok privada, volte ao ShortsFlow e recarregue as opções. "
    "Para publicar automaticamente em modo público, conclua a auditoria do app no TikTok for Developers. "
    "Enquanto a conta permanecer pública, o TikTok só permite ao ShortsFlow tentar o fluxo de Upload/Caixa de Entrada/Rascunhos com o escopo video.upload."
)
PRIVATE_ACCOUNT_AUDIT_BLOCK_REASON = (
    "O app da Content Posting API ainda não está auditado, mas esta conta TikTok foi identificada como privada. "
    "O ShortsFlow pode testar o Direct Post real em 'Somente eu'. Para publicação pública automática, conclua a auditoria do app."
)
DRAFT_UPLOAD_RETRY_GRACE_MINUTES = 5
DRAFT_RETRY_MESSAGE = (
    "O TikTok retornou SEND_TO_USER_INBOX para este envio, mas isso confirma apenas uma notificação de Caixa de Entrada/Rascunho; "
    "não confirma que o vídeo apareceu no celular nem que foi publicado. Como o TikTok não retornou PUBLISH_COMPLETE, "
    "o ShortsFlow liberou este corte para seleção e reenvio. Ele só será removido da tela quando o TikTok confirmar a publicação."
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
    """Remember that Direct Post is audit-blocked so queued items can respect TikTok's restrictions."""
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
    """Expose the only policy-compliant test mode while the TikTok client is unaudited.

    TikTok requires unaudited Direct Post clients to use a private creator
    account and SELF_ONLY viewership. A public account can only use the Upload
    flow until the app is audited or the creator makes the account private.
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


def recover_retryable_draft_uploads(db: Session, *, user_id: int | None = None, commit: bool = True) -> int:
    """Release TikTok Upload/inbox attempts that cannot become automatic posts.

    The Upload endpoint can only place a notification in TikTok's inbox. If the
    app is unaudited and the creator does not see that notification, keeping the
    clip locked as "processing" leaves the user with no recovery path.
    """
    cutoff = _utcnow() - timedelta(minutes=DRAFT_UPLOAD_RETRY_GRACE_MINUTES)
    query = db.query(TikTokPost).filter(
        or_(
            TikTokPost.status == "draft_sent",
            and_(
                TikTokPost.status.in_(["processing", "submitted"]),
                TikTokPost.privacy_level == "DRAFT_INBOX",
                TikTokPost.updated_at <= cutoff,
            ),
        )
    )
    if user_id is not None:
        query = query.filter(TikTokPost.user_id == int(user_id))

    changed = 0
    for post in query.order_by(TikTokPost.user_id.asc(), TikTokPost.id.asc()).all():
        post.status = "ready"
        post.publish_id = None
        post.error = DRAFT_RETRY_MESSAGE
        changed += 1

    if changed and commit:
        db.commit()
    return changed


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
                and_(TikTokPost.status.in_(["processing", "submitted"]), TikTokPost.publish_id.is_(None)),
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
                "Para testar Direct Post, deixe a conta TikTok privada e use 'Somente eu'; para posts públicos, conclua a auditoria do app."
            )
        else:
            post.status = "ready"
            post.error = None
        post.publish_id = None
        changed += 1
    db.commit()
    return changed
