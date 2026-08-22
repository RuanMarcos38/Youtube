import json
from pathlib import Path
from ..config import settings
from ..models import Clip, Job


def clip_to_dict(clip: Clip) -> dict:
    try:
        tags = json.loads(clip.tags_json or "[]")
    except json.JSONDecodeError:
        tags = []

    path = Path(clip.file_path)
    user_root = settings.data_path / "users" / str(clip.user_id)
    try:
        relative = path.resolve().relative_to(user_root.resolve()).as_posix()
        media_url = f"/api/media/{relative}"
    except ValueError:
        media_url = ""

    return {
        "id": clip.id,
        "job_id": clip.job_id,
        "start_seconds": clip.start_seconds,
        "end_seconds": clip.end_seconds,
        "hook": clip.hook,
        "reason": clip.reason,
        "title": clip.title,
        "description": clip.description,
        "copy": clip.copy_text,
        "tags": tags,
        "media_url": media_url,
        "status": clip.status,
        "youtube_video_id": clip.youtube_video_id,
        "upload_error": clip.upload_error,
        "created_at": clip.created_at,
    }


def job_to_dict(job: Job) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
        "requested_clips": job.requested_clips,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "source_video": job.source_video,
        "clips": [clip_to_dict(clip) for clip in sorted(job.clips, key=lambda c: c.id)],
    }
