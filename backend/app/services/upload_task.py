import json
from pathlib import Path

from sqlalchemy.orm import joinedload

from ..database import SessionLocal
from ..models import Clip, Job
from .seo_service import build_publish_metadata
from .youtube_upload import upload_video


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

        # Persist normalized title/tags so the review UI and the actual upload stay aligned.
        clip.title = metadata.title
        clip.tags_json = json.dumps(metadata.tags, ensure_ascii=False)
        db.commit()

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
        db.commit()
    except Exception as exc:
        db.rollback()
        clip = db.get(Clip, clip_id)
        if clip:
            clip.status = "upload_failed"
            clip.upload_error = str(exc)
            db.commit()
    finally:
        db.close()
