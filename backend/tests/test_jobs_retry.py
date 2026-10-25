import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models import Job, SourceVideo, Tenant, TenantPlan, User
from app.routers import jobs as jobs_router


@pytest.fixture(autouse=True)
def healthy_retry_runtime(monkeypatch):
    monkeypatch.setattr(jobs_router.settings, "environment", "production")
    monkeypatch.setattr(jobs_router, "_worker_alive", lambda: True)
    monkeypatch.setattr(jobs_router, "residential_status", lambda _: {"enabled": False, "connected": False})
    monkeypatch.setattr(jobs_router, "permanent_proxy_url", lambda: "")
    monkeypatch.setattr(jobs_router, "download_access_configured", lambda: True)


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
        assert db.get(Job, failed.id).error == failed.error

        repeated = jobs_router.retry_job(failed.id, user=user, db=db)
        assert repeated["id"] == result["id"]
        assert db.query(Job).count() == 2
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


@pytest.mark.parametrize("status", ["ready_for_review", "queued", "rendering"])
def test_retry_rejects_ineligible_status(status):
    db = _session()
    try:
        user, failed = _user_with_failed_job(db)
        failed.status = status
        db.commit()
        with pytest.raises(HTTPException) as error:
            jobs_router.retry_job(failed.id, user=user, db=db)
        assert error.value.status_code == 409
        assert db.query(Job).count() == 1
    finally:
        db.close()


def test_retry_authorization_and_missing_job():
    db = _session()
    try:
        user, failed = _user_with_failed_job(db)
        other = User(tenant_id=user.tenant_id, email="other@example.com", password_hash="hash", display_name="Other")
        db.add(other)
        db.commit()
        with pytest.raises(HTTPException) as error:
            jobs_router.retry_job(failed.id, user=other, db=db)
        assert error.value.status_code == 403
        tenant = Tenant(name="Other tenant")
        db.add(tenant)
        db.flush()
        other.tenant_id = tenant.id
        db.commit()
        with pytest.raises(HTTPException) as error:
            jobs_router.retry_job(failed.id, user=other, db=db)
        assert error.value.status_code == 404
        with pytest.raises(HTTPException) as error:
            jobs_router.retry_job(failed.id + 1000, user=user, db=db)
        assert error.value.status_code == 404
        assert db.query(Job).count() == 1
    finally:
        db.close()


@pytest.mark.parametrize("unavailable", ["worker", "download_auth"])
def test_retry_unavailable_dependency_does_not_create_job(monkeypatch, unavailable):
    from app.models import SystemSetting
    if unavailable == "worker":
        monkeypatch.setattr(jobs_router, "_worker_alive", lambda: False)
    elif unavailable == "residential":
        monkeypatch.setattr(jobs_router, "residential_status", lambda _: {"enabled": True, "connected": False})
    else:
        monkeypatch.setattr(jobs_router, "download_access_configured", lambda: False)
    db = _session()
    try:
        user, failed = _user_with_failed_job(db)
        with pytest.raises(HTTPException) as error:
            jobs_router.retry_job(failed.id, user=user, db=db)
        assert error.value.status_code == 503
        assert db.query(Job).count() == 1
        assert db.query(SystemSetting).count() == 0
    finally:
        db.close()


@pytest.mark.parametrize("connected,permanent", [(True, ""), (False, "http://proxy.example:8080"), (False, "")])
def test_retry_available_acquisition_path(monkeypatch, connected, permanent):
    monkeypatch.setattr(jobs_router, "residential_status", lambda _: {"enabled": True, "connected": connected})
    monkeypatch.setattr(jobs_router, "permanent_proxy_url", lambda: permanent)
    db = _session()
    try:
        user, failed = _user_with_failed_job(db)
        result = jobs_router.retry_job(failed.id, user=user, db=db)
        assert result["status"] == "queued"
    finally:
        db.close()


def test_retry_relationship_survives_reload_and_terminal_attempt():
    db = _session()
    try:
        user, failed = _user_with_failed_job(db)
        original_id, user_id = failed.id, user.id
        result = jobs_router.retry_job(original_id, user=user, db=db)
        attempt = db.get(Job, result["id"])
        attempt.status = "ready_for_review"
        db.commit()
        db.expunge_all()
        repeated = jobs_router.retry_job(original_id, user=db.get(User, user_id), db=db)
        assert repeated["id"] == result["id"]
        assert repeated["status"] == "ready_for_review"
        assert db.query(Job).count() == 2
    finally:
        db.close()


def test_simultaneous_retries_create_one_attempt(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine = create_engine(f"sqlite:///{tmp_path / 'retry.db'}", connect_args={"check_same_thread": False, "timeout": 15})
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    with sessions() as db:
        user, failed = _user_with_failed_job(db)
        user_id, job_id = user.id, failed.id
    barrier = Barrier(2)
    def retry():
        with sessions() as db:
            user = db.get(User, user_id)
            barrier.wait(timeout=5)
            return jobs_router.retry_job(job_id, user=user, db=db)["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: retry(), range(2)))
    assert results[0] == results[1]
    with sessions() as db:
        assert db.query(Job).count() == 2
        assert db.get(Job, job_id).status == "failed"
    engine.dispose()


def test_retry_http_validation_and_expired_session():
    from datetime import datetime, timedelta, timezone
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.auth import _token_hash
    from app.models import UserSession
    app = FastAPI()
    app.include_router(jobs_router.router)
    db = _session()
    try:
        user, failed = _user_with_failed_job(db)
        app.dependency_overrides[jobs_router.get_db] = lambda: db
        client = TestClient(app)
        assert client.post(f"/jobs/{failed.id}/retry").status_code == 401
        db.add(UserSession(user_id=user.id, token_hash=_token_hash("expired"), expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
        assert client.post(f"/jobs/{failed.id}/retry", headers={"Authorization": "Bearer expired"}).status_code == 401
        app.dependency_overrides[jobs_router.get_current_user] = lambda: user
        assert client.post("/jobs/invalid/retry").status_code == 422
        response = client.post(f"/jobs/{failed.id}/retry")
        assert response.status_code == 202
        assert response.json()["status"] == "queued"
        assert client.post(f"/jobs/{failed.id}/retry").json()["id"] == response.json()["id"]
    finally:
        db.close()
