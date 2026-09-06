import json
import uuid
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Clip, Job, SourceVideo, SystemSetting, Tenant, User
from app.services.database_bootstrap import initialize_database
from app.services.youtube_upload_availability import mark_upload_blocked, upload_availability


def _uploaded_clip_fixture(db, *, uploaded_hours_ago: int = 5):
    suffix = uuid.uuid4().hex[:12]
    tenant = Tenant(name=f"YouTube availability {suffix}", billing_status="active")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"youtube-availability-{suffix}@example.com",
        password_hash="test-only",
        display_name="YouTube Availability Test",
        role="member",
        active=True,
    )
    db.add(user)
    db.flush()
    source = SourceVideo(
        tenant_id=tenant.id,
        user_id=user.id,
        youtube_id=f"source-{suffix}",
        title="Source",
        channel_title="Channel",
        original_url="https://www.youtube.com/watch?v=test",
        thumbnail_url="",
        duration_seconds=60,
        rights_confirmed=True,
    )
    db.add(source)
    db.flush()
    job = Job(
        tenant_id=tenant.id,
        user_id=user.id,
        source_video_id=source.id,
        requested_clips=1,
        status="ready_for_review",
        progress=100,
    )
    db.add(job)
    db.flush()
    uploaded_at = datetime.now(timezone.utc) - timedelta(hours=uploaded_hours_ago)
    clip = Clip(
        tenant_id=tenant.id,
        user_id=user.id,
        job_id=job.id,
        start_seconds=0,
        end_seconds=30,
        title="Short uploaded",
        file_path=f"/tmp/{suffix}.mp4",
        status="uploaded",
        youtube_video_id=f"youtube-{suffix}",
        updated_at=uploaded_at,
    )
    db.add(clip)
    db.commit()
    return user, clip, uploaded_at


def test_new_block_uses_last_successful_upload_time():
    initialize_database()
    db = SessionLocal()
    try:
        user, _, uploaded_at = _uploaded_clip_fixture(db, uploaded_hours_ago=5)
        value = mark_upload_blocked(
            db,
            user.id,
            "O limite diário de uploads deste canal foi atingido.",
        )

        assert value["blocked"] is True
        assert value["reference_upload_at"] is not None
        reference = datetime.fromisoformat(value["reference_upload_at"].replace("Z", "+00:00"))
        blocked_until = datetime.fromisoformat(value["blocked_until"].replace("Z", "+00:00"))
        assert abs((reference - uploaded_at).total_seconds()) < 2
        assert abs((blocked_until - (uploaded_at + timedelta(hours=24))).total_seconds()) < 2
        assert 18 * 3600 < value["seconds_remaining"] < 20 * 3600
    finally:
        db.close()


def test_existing_legacy_block_is_shortened_to_last_upload_time():
    initialize_database()
    db = SessionLocal()
    try:
        user, _, uploaded_at = _uploaded_clip_fixture(db, uploaded_hours_ago=5)
        detected_at = datetime.now(timezone.utc)
        legacy_payload = {
            "blocked_at": detected_at.isoformat(),
            "blocked_until": (detected_at + timedelta(hours=24)).isoformat(),
            "message": "O limite diário de uploads deste canal foi atingido.",
        }
        db.add(
            SystemSetting(
                key=f"youtube.upload_block.{user.id}",
                value=json.dumps(legacy_payload),
                secret=False,
            )
        )
        db.commit()

        value = upload_availability(db, user.id)

        assert value["blocked"] is True
        assert value["reference_upload_at"] is not None
        corrected_until = datetime.fromisoformat(value["blocked_until"].replace("Z", "+00:00"))
        assert abs((corrected_until - (uploaded_at + timedelta(hours=24))).total_seconds()) < 2
        assert 18 * 3600 < value["seconds_remaining"] < 20 * 3600
    finally:
        db.close()


def test_existing_legacy_block_is_cleared_when_last_upload_window_passed():
    initialize_database()
    db = SessionLocal()
    try:
        user, _, _ = _uploaded_clip_fixture(db, uploaded_hours_ago=25)
        detected_at = datetime.now(timezone.utc) - timedelta(hours=6)
        legacy_payload = {
            "blocked_at": detected_at.isoformat(),
            "blocked_until": (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat(),
            "message": "O limite diário de uploads deste canal foi atingido.",
        }
        db.add(
            SystemSetting(
                key=f"youtube.upload_block.{user.id}",
                value=json.dumps(legacy_payload),
                secret=False,
            )
        )
        db.commit()

        value = upload_availability(db, user.id)

        assert value["blocked"] is False
        assert value["reference_upload_at"] is not None
        assert value["seconds_remaining"] == 0
    finally:
        db.close()
