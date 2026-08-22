import pytest
from pydantic import ValidationError

from app.schemas import JobCreate


def _job_payload(requested_clips: int) -> dict:
    return {
        "video_id": "abc123",
        "title": "Vídeo de teste",
        "channel_title": "Canal",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "url": "https://www.youtube.com/watch?v=abc123",
        "requested_clips": requested_clips,
        "rights_confirmed": True,
    }


def test_job_create_accepts_ten_shorts():
    job = JobCreate(**_job_payload(10))
    assert job.requested_clips == 10


def test_job_create_rejects_more_than_ten_shorts():
    with pytest.raises(ValidationError):
        JobCreate(**_job_payload(11))
