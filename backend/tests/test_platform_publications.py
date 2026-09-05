import uuid

from app.database import SessionLocal
from app.models import Clip, Job, SourceVideo, Tenant, TikTokPost, User
from app.routers.publications import tiktok_publications, youtube_publications
from app.services.database_bootstrap import initialize_database
from app.services.tiktok_upload_task import refresh_tiktok_post
from app.services.youtube_upload_availability import mark_upload_blocked, upload_availability


def _fixture(db):
    suffix = uuid.uuid4().hex[:12]
    tenant = Tenant(name=f"Platforms {suffix}", billing_status="active")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"platforms-{suffix}@example.com",
        password_hash="test-only",
        display_name="Platform Test",
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
    clip = Clip(
        tenant_id=tenant.id,
        user_id=user.id,
        job_id=job.id,
        start_seconds=0,
        end_seconds=30,
        title="Short",
        file_path=f"/tmp/{suffix}.mp4",
        status="ready",
    )
    db.add(clip)
    db.commit()
    return user, clip


def test_platform_queues_are_independent():
    initialize_database()
    db = SessionLocal()
    try:
        user, clip = _fixture(db)
        clip.status = "uploaded"
        clip.youtube_video_id = "youtube-ok"
        db.commit()

        youtube = youtube_publications(user=user, db=db)
        tiktok = tiktok_publications(user=user, db=db)
        assert clip.id not in {item["id"] for item in youtube["clips"]}
        assert clip.id in {item["id"] for item in tiktok["clips"]}

        db.add(TikTokPost(user_id=user.id, clip_id=clip.id, privacy_level="SELF_ONLY", status="published", publish_id="pub-ok"))
        db.commit()
        tiktok_after = tiktok_publications(user=user, db=db)
        assert clip.id not in {item["id"] for item in tiktok_after["clips"]}
    finally:
        db.close()


def test_youtube_daily_block_records_retry_window():
    initialize_database()
    db = SessionLocal()
    try:
        user, _ = _fixture(db)
        mark_upload_blocked(db, user.id, "O limite diário de uploads deste canal foi atingido.")
        value = upload_availability(db, user.id)
        assert value["blocked"] is True
        assert value["seconds_remaining"] > 23 * 3600
        assert value["blocked_until"]
    finally:
        db.close()


def test_tiktok_inbox_delivery_stays_visible_until_user_finishes_post(monkeypatch):
    initialize_database()
    db = SessionLocal()
    try:
        user, clip = _fixture(db)
        post = TikTokPost(
            user_id=user.id,
            clip_id=clip.id,
            privacy_level="DRAFT_INBOX",
            status="processing",
            publish_id=f"pub-{uuid.uuid4().hex[:8]}",
        )
        db.add(post)
        db.commit()
        post_id = post.id
    finally:
        db.close()

    monkeypatch.setattr(
        "app.services.tiktok_upload_task.fetch_post_status",
        lambda db, user_id, publish_id: {
            "status": "SEND_TO_USER_INBOX",
            "fail_reason": "",
            "post_ids": [],
            "uploaded_bytes": 100,
        },
    )
    refresh_tiktok_post(post_id)

    db = SessionLocal()
    try:
        refreshed = db.get(TikTokPost, post_id)
        owner = db.get(User, refreshed.user_id)
        assert refreshed.status == "processing"
        assert "Rascunho entregue ao TikTok" in (refreshed.error or "")
        queue = tiktok_publications(user=owner, db=db)["clips"]
        item = next(value for value in queue if value["id"] == clip.id)
        assert item["tiktok_status"] == "processing"
        assert "Caixa de Entrada" in (item["tiktok_error"] or "")
    finally:
        db.close()


def test_tiktok_post_only_disappears_after_publish_complete(monkeypatch):
    initialize_database()
    db = SessionLocal()
    try:
        user, clip = _fixture(db)
        post = TikTokPost(
            user_id=user.id,
            clip_id=clip.id,
            privacy_level="SELF_ONLY",
            status="processing",
            publish_id=f"pub-{uuid.uuid4().hex[:8]}",
        )
        db.add(post)
        db.commit()
        post_id = post.id
    finally:
        db.close()

    monkeypatch.setattr(
        "app.services.tiktok_upload_task.fetch_post_status",
        lambda db, user_id, publish_id: {
            "status": "PUBLISH_COMPLETE",
            "fail_reason": "",
            "post_ids": ["123"],
            "uploaded_bytes": 100,
        },
    )
    refresh_tiktok_post(post_id)

    db = SessionLocal()
    try:
        refreshed = db.get(TikTokPost, post_id)
        assert refreshed.status == "published"
        assert refreshed.error is None
    finally:
        db.close()


def test_tiktok_public_post_disappears_after_publish_complete_without_public_id(monkeypatch):
    initialize_database()
    db = SessionLocal()
    try:
        user, clip = _fixture(db)
        post = TikTokPost(
            user_id=user.id,
            clip_id=clip.id,
            privacy_level="PUBLIC_TO_EVERYONE",
            status="processing",
            publish_id=f"pub-{uuid.uuid4().hex[:8]}",
        )
        db.add(post)
        db.commit()
        post_id = post.id
        assert clip.id in {item["id"] for item in tiktok_publications(user=user, db=db)["clips"]}
    finally:
        db.close()

    monkeypatch.setattr(
        "app.services.tiktok_upload_task.fetch_post_status",
        lambda db, user_id, publish_id: {
            "status": "PUBLISH_COMPLETE",
            "fail_reason": "",
            "post_ids": [],
            "uploaded_bytes": 100,
        },
    )
    refresh_tiktok_post(post_id)

    db = SessionLocal()
    try:
        refreshed = db.get(TikTokPost, post_id)
        user = refreshed and refreshed.user_id
        assert refreshed.status == "published"
        assert refreshed.error is None
        owner = db.get(User, user)
        assert owner is not None
        assert clip.id not in {item["id"] for item in tiktok_publications(user=owner, db=db)["clips"]}
    finally:
        db.close()
