import json
from pathlib import Path
from ..database import SessionLocal
from ..models import Clip
from .youtube_upload import upload_video


def run_upload(clip_id: int, privacy_status: str) -> None:
    db = SessionLocal()
    try:
        clip = db.get(Clip, clip_id)
        if not clip:
            return
        clip.status = "uploading"
        clip.upload_error = None
        db.commit()

        tags = json.loads(clip.tags_json or "[]")
        video_id = upload_video(
            Path(clip.file_path),
            clip.title,
            f"{clip.description.rstrip()}\n\n{clip.copy_text.strip()}".strip(),
            tags,
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
