from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Job, SourceVideo, Tenant, TenantPlan, User
from app.routers import jobs as jobs_router


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    return session()


def _user_with_failed_job(db):
    tenant = Tenant(name="Retry tenant", billing_status="active")
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email="retry@example.com",
        password_hash="hash",
        display_name="Retry user",
        role="owner",
        active=True,
    )
    plan = TenantPlan(
        tenant_id=tenant.id,
        plan_code="starter",
        billing_status="active",
        monthly_job_limit=10,
        unlimited=False,
    )
    db.add_all([user, plan])
    db.flush()
    source = SourceVideo(
        tenant_id=tenant.id,
        user_id=user.id,
        youtube_id="abc123def45",
        title="Original video",
        channel_title="Channel",
        original_url="https://www.youtube.com/watch?v=abc123def45",
        thumbnail_url="https://img.youtube.com/vi/abc123def45/hqdefault.jpg",
        rights_confirmed=True,
    )
    db.add(source)
    db.flush()
    failed = Job(
        tenant_id=tenant.id,
        user_id=user.id,
        source_video_id=source.id,
        requested_clips=10,
        status="failed",
        progress=100,
        error="OpenAI clip selection failed: rate_limit_exceeded tokens per min",
    )
    db.add(failed)
    db.commit()
    return user, failed


def test_retry_failed_job_creates_new_queued_job(monkeypatch):
    monkeypatch.setattr(jobs_router.settings, "environment", "production")
    monkeypatch.setattr(jobs_router, "download_access_configured", lambda: True)
    db = _session()
    try:
        user, failed = _user_with_failed_job(db)

        result = jobs_router.retry_job(failed.id, user=user, db=db)

        assert result["id"] != failed.id
        assert result["status"] == "queued"
        assert result["progress"] == 0
        assert result["error"] is None
        assert result["requested_clips"] == 10
        jobs = db.query(Job).order_by(Job.id.asc()).all()
        assert [job.status for job in jobs] == ["failed", "queued"]
    finally:
        db.close()


def test_retry_rejects_running_job(monkeypatch):
    monkeypatch.setattr(jobs_router.settings, "environment", "development")
    db = _session()
    try:
        user, failed = _user_with_failed_job(db)
        failed.status = "transcribing"
        db.commit()

        try:
            jobs_router.retry_job(failed.id, user=user, db=db)
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("retry_job should reject non-failed jobs")
    finally:
        db.close()


def test_delete_failed_job_removes_record_and_workdir_but_keeps_source(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_router.settings, "data_dir", str(tmp_path))
    db = _session()
    try:
        user, failed = _user_with_failed_job(db)
        job_id = failed.id
        source_id = failed.source_video_id
        work_dir = tmp_path / "users" / str(user.id) / "jobs" / str(job_id)
        work_dir.mkdir(parents=True)
        (work_dir / "partial.tmp").write_text("incomplete", encoding="utf-8")

        result = jobs_router.delete_failed_job(job_id, user=user, db=db)

        assert result is None
        assert db.get(Job, job_id) is None
        assert db.get(SourceVideo, source_id) is not None
        assert not work_dir.exists()
    finally:
        db.close()


def test_delete_rejects_running_job():
    db = _session()
    try:
        user, failed = _user_with_failed_job(db)
        failed.status = "rendering"
        db.commit()

        try:
            jobs_router.delete_failed_job(failed.id, user=user, db=db)
        except HTTPException as exc:
            assert exc.status_code == 409
        else:
            raise AssertionError("delete_failed_job should reject non-failed jobs")
    finally:
        db.close()
