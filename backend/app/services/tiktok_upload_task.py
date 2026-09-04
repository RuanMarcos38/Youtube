from pathlib import Path

from ..database import SessionLocal
from ..models import Clip, TikTokPost
from .tiktok_upload import TikTokPostLimitError, direct_post_video


def _pause_user_queue(db, user_id: int, message: str, current_post_id: int) -> None:
    current = db.get(TikTokPost, current_post_id)
    if current:
        current.status = "paused_limit"
        current.error = message
    for queued in db.query(TikTokPost).filter(TikTokPost.user_id == user_id, TikTokPost.status == "queued").all():
        queued.status = "paused_limit"
        queued.error = message
    db.commit()


def run_tiktok_upload(post_id: int) -> None:
    db = SessionLocal()
    try:
        post = db.get(TikTokPost, post_id)
        if not post:
            return
        clip = db.query(Clip).filter(Clip.id == post.clip_id, Clip.user_id == post.user_id).first()
        if not clip:
            post.status = "failed"
            post.error = "Corte não encontrado para publicar no TikTok."
            db.commit()
            return

        post.status = "uploading"
        post.error = None
        db.commit()
        publish_id = direct_post_video(
            db,
            user_id=post.user_id,
            file_path=Path(clip.file_path),
            title=post.title,
            privacy_level=post.privacy_level,
            disable_comment=post.disable_comment,
            disable_duet=post.disable_duet,
            disable_stitch=post.disable_stitch,
        )
        post.status = "submitted"
        post.publish_id = publish_id
        post.error = None
        db.commit()
    except TikTokPostLimitError as exc:
        db.rollback()
        post = db.get(TikTokPost, post_id)
        if post:
            _pause_user_queue(db, post.user_id, str(exc), post_id)
    except Exception as exc:
        db.rollback()
        post = db.get(TikTokPost, post_id)
        if post:
            post.status = "failed"
            post.error = str(exc)
            db.commit()
    finally:
        db.close()
