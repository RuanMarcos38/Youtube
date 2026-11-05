from pathlib import Path

import pytest

from app.services import local_uploads


def test_local_source_roundtrip_is_user_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(local_uploads.settings, "data_dir", str(tmp_path))
    upload_id = "a" * 32
    path = local_uploads.upload_path(51, upload_id, ".mp4")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"valid-media-fixture")
    reference = local_uploads.source_reference(upload_id, ".mp4")
    assert local_uploads.is_local_source(reference)
    assert local_uploads.resolve_local_source(reference, 51) == path
    with pytest.raises(FileNotFoundError):
        local_uploads.resolve_local_source(reference, 52)


def test_rejects_path_traversal_and_invalid_format():
    with pytest.raises((ValueError, AttributeError)):
        local_uploads.source_reference("../outside", ".mp4")
    with pytest.raises(ValueError):
        local_uploads.upload_path(1, "a" * 32, ".exe")
    with pytest.raises(ValueError):
        local_uploads.resolve_local_source("shortsflow-upload:../../etc/passwd", 1)


def test_external_youtube_urls_are_not_uploaded_sources():
    assert not local_uploads.is_local_source("https://www.youtube.com/watch?v=example")


def test_retrying_local_upload_does_not_require_youtube_download(monkeypatch):
    from app.routers import jobs as jobs_router
    from app.models import User
    from app.database import Base
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    monkeypatch.setattr(jobs_router.settings, "environment", "production")
    monkeypatch.setattr(jobs_router, "download_access_configured", lambda: False)
    monkeypatch.setattr(jobs_router, "can_use_tool", lambda db, user: (True, ""))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        user = User(id=1, tenant_id=1, role="superadmin")
        jobs_router._ensure_job_can_be_queued(user, db, 120, 2, local_upload=True)
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            jobs_router._ensure_job_can_be_queued(user, db, 120, 2)
        assert exc.value.status_code == 503
    finally:
        db.close()
