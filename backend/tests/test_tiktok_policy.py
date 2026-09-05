import uuid

from app.database import SessionLocal
from app.models import Clip, Job, SourceVideo, SystemSetting, Tenant, TikTokPost, User
from app.services.database_bootstrap import initialize_database
from app.services.tiktok_policy import (
    PUBLIC_AUDIT_SETTING_PREFIX,
    clear_legacy_unaudited_state,
    is_unaudited_error_text,
    release_unaudited_public_queue,
)


def test_detects_tiktok_unaudited_api_code():
    assert is_unaudited_error_text("unaudited_client_can_only_post_to_private_accounts")


def test_detects_legacy_portuguese_unaudited_message():
    assert is_unaudited_error_text("TikTok: o app ainda está marcado como não auditado.")


def test_does_not_confuse_rate_limit_with_audit_restriction():
    assert not is_unaudited_error_text("rate_limit_exceeded")


def test_clear_legacy_unaudited_state_removes_old_public_gate():
    initialize_database()
    user_id = int(uuid.uuid4().hex[:8], 16)
    db = SessionLocal()
    try:
        key = f"{PUBLIC_AUDIT_SETTING_PREFIX}{user_id}"
        db.add(SystemSetting(key=key, value="2026-09-05T12:00:00+00:00", secret=False))
        db.commit()

        clear_legacy_unaudited_state(db, user_id=user_id)

        assert db.get(SystemSetting, key) is None
    finally:
        db.close()


def test_release_unaudited_public_queue_does_not_keep_local_public_gate():
    initialize_database()
    user_id = int(uuid.uuid4().hex[:8], 16)
    db = SessionLocal()
    try:
        key = f"{PUBLIC_AUDIT_SETTING_PREFIX}{user_id}"
        db.add(SystemSetting(key=key, value="2026-09-05T12:00:00+00:00", secret=False))
        db.commit()

        changed = release_unaudited_public_queue(db, user_id=user_id, current_post_id=0)

        assert changed == 0
        assert db.get(SystemSetting, key) is None
    finally:
        db.close()


def test_release_unaudited_public_queue_keeps_current_error_visible():
    initialize_database()
    suffix = uuid.uuid4().hex[:12]
    db = SessionLocal()
    try:
        tenant = Tenant(name=f"TikTok policy {suffix}", billing_status="active")
        db.add(tenant)
        db.flush()
        user = User(
            tenant_id=tenant.id,
            email=f"tiktok-policy-{suffix}@example.com",
            password_hash="test-only",
            display_name="TikTok Policy",
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
            requested_clips=2,
            status="ready_for_review",
            progress=100,
        )
        db.add(job)
        db.flush()
        first = Clip(
            tenant_id=tenant.id,
            user_id=user.id,
            job_id=job.id,
            start_seconds=0,
            end_seconds=30,
            title="First",
            file_path=f"/tmp/{suffix}-1.mp4",
            status="ready",
        )
        second = Clip(
            tenant_id=tenant.id,
            user_id=user.id,
            job_id=job.id,
            start_seconds=30,
            end_seconds=60,
            title="Second",
            file_path=f"/tmp/{suffix}-2.mp4",
            status="ready",
        )
        third = Clip(
            tenant_id=tenant.id,
            user_id=user.id,
            job_id=job.id,
            start_seconds=60,
            end_seconds=90,
            title="Third",
            file_path=f"/tmp/{suffix}-3.mp4",
            status="ready",
        )
        db.add_all([first, second, third])
        db.flush()
        current = TikTokPost(
            user_id=user.id,
            clip_id=first.id,
            privacy_level="PUBLIC_TO_EVERYONE",
            status="uploading",
        )
        queued = TikTokPost(
            user_id=user.id,
            clip_id=second.id,
            privacy_level="PUBLIC_TO_EVERYONE",
            status="queued",
        )
        private_processing = TikTokPost(
            user_id=user.id,
            clip_id=third.id,
            privacy_level="SELF_ONLY",
            status="processing",
            publish_id="private-publish-id",
            error="TikTok recebeu o arquivo e está processando/moderando a publicação.",
        )
        db.add_all([current, queued, private_processing])
        db.commit()

        changed = release_unaudited_public_queue(
            db,
            user_id=user.id,
            current_post_id=current.id,
            current_error="TikTok recusou app não auditado.",
        )

        assert changed == 2
        assert current.status == "failed"
        assert current.error == "TikTok recusou app não auditado."
        assert queued.status == "ready"
        assert queued.error is None
        assert private_processing.status == "processing"
        assert private_processing.publish_id == "private-publish-id"
        assert private_processing.error == "TikTok recebeu o arquivo e está processando/moderando a publicação."
    finally:
        db.close()
