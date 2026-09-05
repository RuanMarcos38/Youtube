from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Clip, SystemSetting, TikTokPost, User
from ..services.database_bootstrap import PUBLICATIONS_RESET_KEY
from ..services.serializers import clip_to_dict
from ..services.tiktok_policy import recover_retryable_draft_uploads
from ..services.youtube_upload_availability import upload_availability


router = APIRouter(prefix="/publications", tags=["publications"])


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _reset_at(user: User, db: Session) -> datetime | None:
    if user.role != "superadmin":
        return None
    marker = db.get(SystemSetting, PUBLICATIONS_RESET_KEY)
    if not marker or not marker.value:
        return None
    try:
        return _utc(datetime.fromisoformat(marker.value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _base_clips(user: User, db: Session) -> list[Clip]:
    rows = (
        db.query(Clip)
        .filter(Clip.user_id == user.id)
        .order_by(Clip.id.desc())
        .limit(200)
        .all()
    )
    reset = _reset_at(user, db)
    if reset is not None:
        rows = [row for row in rows if _utc(row.created_at) >= reset]
    return rows


@router.get("/youtube")
def youtube_publications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the YouTube queue independently from the TikTok queue."""
    rows = [clip for clip in _base_clips(user, db) if clip.status not in {"uploaded", "archived"}]
    return {
        "platform": "youtube",
        "availability": upload_availability(db, user.id),
        "clips": [clip_to_dict(clip) for clip in rows],
    }


@router.get("/tiktok")
def tiktok_publications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the same generated Shorts for TikTok without sharing YouTube status.

    No video file is duplicated on disk: both platform tabs reference the same
    rendered Short while keeping publication state independent. A TikTok item
    is removed only after TikTok confirms PUBLISH_COMPLETE. Inbox/draft delivery
    is not treated as a completed publication.
    """
    recover_retryable_draft_uploads(db, user_id=user.id)
    clips = [clip for clip in _base_clips(user, db) if clip.status != "archived"]
    ids = [clip.id for clip in clips]
    posts = {
        post.clip_id: post
        for post in (
            db.query(TikTokPost)
            .filter(TikTokPost.user_id == user.id, TikTokPost.clip_id.in_(ids))
            .all()
            if ids
            else []
        )
    }
    items = []
    for clip in clips:
        post = posts.get(clip.id)
        if post and post.status == "published":
            continue
        payload = clip_to_dict(clip)
        payload["tiktok_status"] = post.status if post else "ready"
        payload["tiktok_error"] = post.error if post else None
        payload["tiktok_publish_id"] = post.publish_id if post else None
        items.append(payload)
    return {"platform": "tiktok", "clips": items}


@router.get("/tiktok/history")
def tiktok_publication_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(TikTokPost)
        .filter(TikTokPost.user_id == user.id)
        .order_by(TikTokPost.id.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": row.id,
            "clip_id": row.clip_id,
            "status": row.status,
            "publish_id": row.publish_id,
            "privacy_level": row.privacy_level,
            "error": row.error,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]
