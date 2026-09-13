import uuid

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import Clip, Job, SourceVideo, Tenant, TikTokPost, User
from app.routers.clip_deletions import BatchDeleteRequest, delete_unpublished_clip, delete_unpublished_clips_batch
from app.services.database_bootstrap import initialize_database


def _workspace(db, tmp_path):
    suffix = uuid.uuid4().hex[:12]
    tenant = Tenant(name=f"Delete Clips {suffix}", billing_status="active")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"delete-clips-{suffix}@example.com",
        password_hash="test-only",
        display_name="Delete Clips Test",
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
        requested_clips=3,
        status="ready_for_review",
        progress=100,
    )
    db.add(job)
    db.flush()

    def add_clip(name: str, status: str = "ready"):
        video_path = tmp_path / f"{name}.mp4"
        subtitle_path = tmp_path / f"{name}.srt"
        video_path.write_bytes(b"video")
        subtitle_path.write_text("1\n00:00:00,000 --> 00:00:01,000\nTeste\n", encoding="utf-8")
        clip = Clip(
            tenant_id=tenant.id,
            user_id=user.id,
            job_id=job.id,
            start_seconds=0,
            end_seconds=30,
            title=name,
            file_path=str(video_path),
            subtitle_path=str(subtitle_path),
            status=status,
        )
        db.add(clip)
        db.flush()
        return clip, video_path, subtitle_path

    return user, job, add_clip


def test_delete_one_removes_only_selected_clip_and_files(tmp_path):
    initialize_database()
    db = SessionLocal()
    try:
        user, job, add_clip = _workspace(db, tmp_path)
        selected, selected_video, selected_subtitle = add_clip("Excluir")
        sibling, sibling_video, _ = add_clip("Manter")
        db.commit()
        selected_id = selected.id
        sibling_id = sibling.id
        job_id = job.id

        delete_unpublished_clip(selected_id, user=user, db=db)

        assert db.get(Clip, selected_id) is None
        assert db.get(Clip, sibling_id) is not None
        assert db.get(Job, job_id) is not None
        assert not selected_video.exists()
        assert not selected_subtitle.exists()
        assert sibling_video.exists()
    finally:
        db.close()


def test_delete_blocks_published_or_active_clip(tmp_path):
    initialize_database()
    db = SessionLocal()
    try:
        user, _, add_clip = _workspace(db, tmp_path)
        published, _, _ = add_clip("Publicado", status="uploaded")
        published.youtube_video_id = "youtube-video-id"
        active, _, _ = add_clip("Em fila", status="upload_queued")
        db.commit()

        with pytest.raises(HTTPException) as published_error:
            delete_unpublished_clip(published.id, user=user, db=db)
        assert published_error.value.status_code == 409

        with pytest.raises(HTTPException) as active_error:
            delete_unpublished_clip(active.id, user=user, db=db)
        assert active_error.value.status_code == 409

        assert db.get(Clip, published.id) is not None
        assert db.get(Clip, active.id) is not None
    finally:
        db.close()


def test_delete_blocks_clip_with_tiktok_history(tmp_path):
    initialize_database()
    db = SessionLocal()
    try:
        user, _, add_clip = _workspace(db, tmp_path)
        clip, _, _ = add_clip("TikTok")
        db.add(TikTokPost(user_id=user.id, clip_id=clip.id, privacy_level="SELF_ONLY", status="failed"))
        db.commit()

        with pytest.raises(HTTPException) as error:
            delete_unpublished_clip(clip.id, user=user, db=db)
        assert error.value.status_code == 409
        assert db.get(Clip, clip.id) is not None
    finally:
        db.close()


def test_batch_delete_removes_only_safe_clips(tmp_path):
    initialize_database()
    db = SessionLocal()
    try:
        user, _, add_clip = _workspace(db, tmp_path)
        first, first_video, _ = add_clip("Primeiro")
        second, second_video, _ = add_clip("Segundo", status="approved")
        protected, protected_video, _ = add_clip("Protegido", status="uploading")
        db.commit()
        first_id, second_id, protected_id = first.id, second.id, protected.id

        result = delete_unpublished_clips_batch(
            BatchDeleteRequest(clip_ids=[first_id, second_id, protected_id, 999999999]),
            user=user,
            db=db,
        )

        assert result["deleted"] == 2
        assert result["skipped"] == 2
        assert set(result["clip_ids"]) == {first_id, second_id}
        assert db.get(Clip, first_id) is None
        assert db.get(Clip, second_id) is None
        assert db.get(Clip, protected_id) is not None
        assert not first_video.exists()
        assert not second_video.exists()
        assert protected_video.exists()
    finally:
        db.close()
