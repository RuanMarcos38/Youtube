import uuid
from pathlib import Path

from app.database import SessionLocal
from app.models import Clip, Job, SourceVideo, Tenant, TikTokPost, User
from app.services import automatic_mode as auto
from app.services import automatic_mode_guard as guard
from app.services.database_bootstrap import initialize_database


def _fixture(tmp_path: Path):
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:12]
    tenant = Tenant(name=f"Auto TikTok {suffix}", billing_status="active")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"auto-tiktok-{suffix}@example.com",
        password_hash="test-only",
        display_name="Auto TikTok",
        role="member",
        active=True,
    )
    db.add(user)
    db.flush()
    source = SourceVideo(
        tenant_id=tenant.id,
        user_id=user.id,
        youtube_id=f"v-{suffix}",
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
    media = tmp_path / f"{suffix}.mp4"
    media.write_bytes(b"not-empty")
    clip = Clip(
        tenant_id=tenant.id,
        user_id=user.id,
        job_id=job.id,
        start_seconds=0,
        end_seconds=30,
        title="Short pronto",
        description="Descrição",
        file_path=str(media),
        subtitle_path="",
        status="ready",
    )
    db.add(clip)
    db.commit()
    return db, user, clip


def _config():
    return auto._normalize_config({
        **auto.DEFAULT_AUTO_CONFIG,
        "enabled": True,
        "publish_tiktok": True,
        "music_usage_confirmed": True,
        "rights_confirmed": True,
        "tiktok_privacy_level": "PUBLIC_TO_EVERYONE",
    })


def _allow_tiktok(monkeypatch):
    monkeypatch.setattr(guard, "tiktok_connection_status", lambda db, user_id: {"connected": True})
    monkeypatch.setattr(
        guard,
        "get_creator_info",
        lambda db, user_id, force=True: {
            "privacy_level_options": ["PUBLIC_TO_EVERYONE", "SELF_ONLY"],
            "comment_disabled": False,
            "duet_disabled": False,
            "stitch_disabled": False,
            "max_video_post_duration_sec": 60,
        },
    )
    monkeypatch.setattr(guard, "clear_legacy_unaudited_state", lambda db, user_id: None)
    monkeypatch.setattr(guard, "recover_retryable_draft_uploads", lambda db, user_id: 0)
    monkeypatch.setattr(guard, "apply_unaudited_public_block", lambda db, user_id, creator: creator)
    monkeypatch.setattr(auto, "expected_publications_now", lambda config: 1)


def test_automatic_tiktok_queues_regular_ready_clip(monkeypatch, tmp_path):
    initialize_database()
    db, user, clip = _fixture(tmp_path)
    try:
        _allow_tiktok(monkeypatch)
        queued, warning = guard._queue_tiktok_due_verified(db, user, _config())
        assert warning is None
        assert queued == 1
        post = db.query(TikTokPost).filter(TikTokPost.user_id == user.id, TikTokPost.clip_id == clip.id).one()
        assert post.status == "queued"
        assert post.privacy_level == "PUBLIC_TO_EVERYONE"
    finally:
        db.close()


def test_automatic_tiktok_reuses_ready_post_without_duplicate(monkeypatch, tmp_path):
    initialize_database()
    db, user, clip = _fixture(tmp_path)
    try:
        existing = TikTokPost(
            user_id=user.id,
            clip_id=clip.id,
            privacy_level="SELF_ONLY",
            status="ready",
            publish_id=None,
            error="retry",
        )
        db.add(existing)
        db.commit()
        existing_id = existing.id

        _allow_tiktok(monkeypatch)
        queued, warning = guard._queue_tiktok_due_verified(db, user, _config())
        assert warning is None
        assert queued == 1
        rows = db.query(TikTokPost).filter(TikTokPost.user_id == user.id, TikTokPost.clip_id == clip.id).all()
        assert len(rows) == 1
        assert rows[0].id == existing_id
        assert rows[0].status == "queued"
        assert rows[0].error is None
    finally:
        db.close()
