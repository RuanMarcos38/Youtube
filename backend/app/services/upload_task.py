import json
from pathlib import Path

from sqlalchemy.orm import joinedload

from ..database import SessionLocal
from ..errors import YouTubeUploadLimitError
from ..models import Clip, Job
from .seo_service import build_publish_metadata
from .youtube_upload import upload_video
from .youtube_upload_availability import mark_upload_blocked


def _pause_user_upload_queue(db, user_id: int, message: str, current_clip_id: int) -> None:
    current = db.get(Clip, current_clip_id)
    if current:
        current.status = "approved"
        current.upload_error = message
        current.upload_privacy = "public"
    for queued in db.query(Clip).filter(Clip.user_id == user_id, Clip.status == "upload_queued").all():
        queued.status = "approved"
        queued.upload_error = message
        queued.upload_privacy = "public"
    db.commit()
    # The provider error is a rolling daily upload cap. Store an estimated
    # retry window separately from credentials/tokens so the UI can count down
    # and stop users from repeatedly sending requests during the block.
    mark_upload_blocked(db, user_id, message, hours=24)


def run_upload(clip_id: int, privacy_status: str) -> None:
    db = SessionLocal()
    try:
        clip = (
            db.query(Clip)
            .options(joinedload(Clip.job).joinedload(Job.source_video))
            .filter(Clip.id == clip_id)
            .first()
        )
        if not clip:
            return
        clip.status = "uploading"
        clip.upload_error = None
        clip.upload_privacy = "public"
        db.commit()

        try:
            stored_tags = json.loads(clip.tags_json or "[]")
            if not isinstance(stored_tags, list):
                stored_tags = []
        except (json.JSONDecodeError, TypeError):
            stored_tags = []

        source_title = clip.job.source_video.title if clip.job and clip.job.source_video else ""
        metadata = build_publish_metadata(
            title=clip.title,
            description=clip.description,
            copy_text=clip.copy_text,
            tags=[str(tag) for tag in stored_tags],
            source_title=source_title,
            hook=clip.hook,
        )

        clip.title = metadata.title
        clip.tags_json = json.dumps(metadata.tags, ensure_ascii=False)
        db.commit()

        privacy_status = "public"
        video_id = upload_video(
            Path(clip.file_path),
            metadata.title,
            metadata.description,
            metadata.tags,
            user_id=clip.user_id,
            privacy_status=privacy_status,
        )
        clip.status = "uploaded"
        clip.youtube_video_id = video_id
        clip.upload_error = None
        db.commit()
    except YouTubeUploadLimitError as exc:
        db.rollback()
        clip = db.get(Clip, clip_id)
        if clip:
            _pause_user_upload_queue(db, clip.user_id, str(exc), clip_id)
    except Exception as exc:
        db.rollback()
        clip = db.get(Clip, clip_id)
        if clip:
            clip.status = "upload_failed"
            clip.upload_error = str(exc)
            db.commit()
    finally:
        db.close()
