from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import SystemSetting, TikTokPost


PUBLIC_AUDIT_RECHECK_SECONDS = 10 * 60
PUBLIC_AUDIT_SETTING_PREFIX = "tiktok_public_audit_block_user_"
UNAUDITED_CODE = "unaudited_client_can_only_post_to_private_accounts"
UNAUDITED_MARKERS = (
    UNAUDITED_CODE,
    "não auditado",
    "nao auditado",
)
PUBLIC_AUDIT_BLOCK_MESSAGE = (
    "O TikTok confirmou no envio que este app da Content Posting API ainda não concluiu "
    "a auditoria exigida para publicação pública. A fila pública não será enviada novamente "
    "até uma nova validação para evitar falhas em lote. Para testar o envio agora, use "
    "'Somente eu'. A opção pública será revalidada automaticamente pelo ShortsFlow."
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _setting_key(user_id: int) -> str:
    return f"{PUBLIC_AUDIT_SETTING_PREFIX}{int(user_id)}"


def is_unaudited_error_text(value: str | None) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and any(marker in text for marker in UNAUDITED_MARKERS)


def record_unaudited_public_block(db: Session, *, user_id: int, when: datetime | None = None) -> None:
    recorded_at = _utc(when or datetime.now(timezone.utc))
    key = _setting_key(user_id)
    marker = db.get(SystemSetting, key)
    if marker is None:
        marker = SystemSetting(key=key, value=recorded_at.isoformat(), secret=False)
        db.add(marker)
    else:
        marker.value = recorded_at.isoformat()
        marker.secret = False


def recent_unaudited_public_block(
    db: Session,
    *,
    user_id: int,
    max_age_seconds: int = PUBLIC_AUDIT_RECHECK_SECONDS,
) -> bool:
    marker = db.get(SystemSetting, _setting_key(user_id))
    if not marker or not marker.value:
        return False
    try:
        recorded_at = _utc(datetime.fromisoformat(str(marker.value).replace("Z", "+00:00")))
    except (TypeError, ValueError):
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, int(max_age_seconds)))
    return recorded_at >= cutoff


def guard_creator_info_for_audit(db: Session, *, user_id: int, creator: dict) -> dict:
    """Apply the client-level audit restriction on top of creator privacy options.

    Creator Info describes what the creator account allows. TikTok can still reject
    PUBLIC_TO_EVERYONE at Direct Post initialization when the API client itself is
    unaudited. A recent authoritative init failure therefore temporarily limits the
    export screen to SELF_ONLY, without permanently hiding public posting after audit.
    """
    result = dict(creator)
    if not recent_unaudited_public_block(db, user_id=user_id):
        return result

    options = [str(item) for item in result.get("privacy_level_options") or []]
    result["privacy_level_options"] = ["SELF_ONLY"] if "SELF_ONLY" in options else []
    return result


def release_unaudited_public_queue(db: Session, *, user_id: int, current_post_id: int) -> int:
    """Undo a public batch after TikTok authoritatively rejects an unaudited client.

    The first failed Direct Post is enough to prove the client-level restriction. All
    queued clips are returned to a clean, retryable state instead of showing the same
    red error dozens of times. No video is silently changed to private.
    """
    record_unaudited_public_block(db, user_id=user_id)
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
        if post.id == current_post_id or post.status in {"queued", "paused_limit", "uploading"}:
            post.status = "ready"
            post.error = None
            post.publish_id = None
            changed += 1
    db.commit()
    return changed


def recover_legacy_unaudited_pauses(db: Session) -> int:
    """Clean the old behavior that copied one audit error to every queued clip."""
    rows = (
        db.query(TikTokPost)
        .filter(TikTokPost.status == "paused_limit", TikTokPost.error.is_not(None))
        .order_by(TikTokPost.user_id.asc(), TikTokPost.id.asc())
        .all()
    )
    affected_users: set[int] = set()
    changed = 0
    for post in rows:
        if not is_unaudited_error_text(post.error):
            continue
        affected_users.add(int(post.user_id))
        post.status = "ready"
        post.error = None
        post.publish_id = None
        changed += 1

    if changed:
        now = datetime.now(timezone.utc)
        for user_id in affected_users:
            record_unaudited_public_block(db, user_id=user_id, when=now)
    return changed
