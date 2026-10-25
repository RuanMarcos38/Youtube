from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.database import Base, get_db
from app.models import Clip, TikTokPost
from app.routers import publications
from test_platform_publications import _fixture


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    user, clip = _fixture(db)
    monkeypatch.setattr(publications.settings, "data_dir", str(tmp_path))
    folder = tmp_path / "users" / str(user.id) / "jobs" / str(clip.job_id)
    folder.mkdir(parents=True)
    video = folder / "clip_01.mp4"
    subtitle = folder / "clip_01.srt"
    source = folder / "source.mp4"
    for path in (video, subtitle, source):
        path.write_bytes(b"test artifact")
    clip.file_path = str(video)
    clip.subtitle_path = str(subtitle)
    clip.status = "uploaded"
    clip.youtube_video_id = "published-id"
    db.commit()
    app = FastAPI()
    app.include_router(publications.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: user
    def database():
        yield db
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield SimpleNamespace(db=db, user=user, clip=clip, video=video, subtitle=subtitle, source=source, client=client, app=app, root=tmp_path)
    db.close()
    engine.dispose()


def clean(runtime, confirmed=True):
    return runtime.client.post(f"/api/publications/youtube/{runtime.clip.id}/clean-local-files", json={"confirmed": confirmed})


def test_cleanup_preserves_publication_history_original_and_is_idempotent(runtime):
    result = clean(runtime)
    assert result.status_code == 200, result.text
    assert result.json()["removed_files"] == 2
    assert result.json()["freed_bytes"] == 26
    assert not runtime.video.exists() and not runtime.subtitle.exists()
    assert runtime.source.read_bytes() == b"test artifact"
    runtime.db.refresh(runtime.clip)
    assert runtime.clip.status == "uploaded" and runtime.clip.youtube_video_id == "published-id"
    assert runtime.clip.file_path == ""
    history = runtime.client.get("/api/publications/youtube/history").json()["clips"]
    assert history[0]["local_files_cleaned"] is True
    assert runtime.client.get("/api/publications/tiktok").json()["clips"] == []
    assert clean(runtime).json()["removed_files"] == 0


@pytest.mark.parametrize("status,video_id", [("ready", None), ("uploading", None), ("upload_failed", None), ("uploaded", None)])
def test_unconfirmed_uploads_are_protected(runtime, status, video_id):
    runtime.clip.status, runtime.clip.youtube_video_id = status, video_id
    runtime.db.commit()
    assert clean(runtime).status_code == 409
    assert runtime.video.exists() and runtime.subtitle.exists()


def test_cleanup_requires_explicit_confirmation(runtime):
    assert clean(runtime, False).status_code == 400
    assert runtime.video.exists()


def test_other_users_cannot_clean_files(runtime):
    runtime.app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=runtime.user.id + 1)
    assert clean(runtime).status_code == 404
    assert runtime.video.exists()


@pytest.mark.parametrize("status", ["queued", "uploading", "processing", "submitted", "ready", "failed"])
def test_pending_tiktok_is_protected(runtime, status):
    runtime.db.add(TikTokPost(user_id=runtime.user.id, clip_id=runtime.clip.id, privacy_level="PUBLIC_TO_EVERYONE", status=status))
    runtime.db.commit()
    assert clean(runtime).status_code == 409
    assert runtime.video.exists()


@pytest.mark.parametrize("unsafe", ["outside", "source", "other_job"])
def test_paths_are_validated_before_any_deletion(runtime, unsafe):
    if unsafe == "outside":
        path = runtime.root / "another-project.srt"
    elif unsafe == "source":
        path = runtime.source
    else:
        path = runtime.video.parent.parent / "999" / "clip_01.srt"
        path.parent.mkdir()
    path.write_bytes(b"protected")
    runtime.clip.subtitle_path = str(path)
    runtime.db.commit()
    assert clean(runtime).status_code == 409
    assert path.read_bytes() == b"protected" and runtime.video.exists()


def test_shared_files_are_protected(runtime):
    other = Clip(tenant_id=runtime.user.tenant_id, user_id=runtime.user.id, job_id=runtime.clip.job_id, start_seconds=0, end_seconds=1, title="Other", file_path=str(runtime.video), status="ready")
    runtime.db.add(other)
    runtime.db.commit()
    assert clean(runtime).status_code == 409
    assert runtime.video.exists()


def test_published_tiktok_allows_cleanup(runtime):
    runtime.db.add(TikTokPost(user_id=runtime.user.id, clip_id=runtime.clip.id, privacy_level="PUBLIC_TO_EVERYONE", status="published", publish_id="tt-ok"))
    runtime.db.commit()
    assert clean(runtime).status_code == 200
    assert runtime.db.query(TikTokPost).first().publish_id == "tt-ok"
