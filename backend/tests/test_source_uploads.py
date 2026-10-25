import json
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_current_user
from app.database import Base, get_db
from app.models import Job, SourceVideo, Tenant, User
from app.routers import jobs
from app.services import pipeline, source_uploads


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    tenant = Tenant(name="Upload test", billing_status="active")
    db.add(tenant)
    db.flush()
    user = User(tenant_id=tenant.id, email="upload@example.test", display_name="Upload test", password_hash="hash", role="superadmin", active=True)
    db.add(user)
    db.commit()
    monkeypatch.setattr(jobs.settings, "data_dir", str(tmp_path / "data"))
    monkeypatch.setattr(jobs.settings, "environment", "production")
    monkeypatch.setattr(jobs, "can_use_tool", lambda *_: (True, ""))
    monkeypatch.setattr(jobs, "download_access_configured", lambda: False)
    monkeypatch.setattr(jobs, "_worker_alive", lambda: True)
    monkeypatch.setattr(jobs, "inspect_uploaded_video", lambda _: 120)
    monkeypatch.setattr(pipeline, "SessionLocal", factory)
    app = FastAPI()
    app.include_router(jobs.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: user
    def database():
        yield db
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield SimpleNamespace(db=db, user=user, app=app, client=client, root=tmp_path)
    db.close()
    engine.dispose()


def submit(runtime, content=b"synthetic source", filename="original.mp4", rights="true", clips="3"):
    return runtime.client.post("/api/jobs/upload", files={"file": (filename, content, "video/mp4")}, data={"rights_confirmed": rights, "requested_clips": clips})


def test_upload_queues_without_youtube_auth_and_retry_keeps_original(runtime):
    response = submit(runtime, filename="../../original.mp4")
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued"
    assert body["source_video"]["duration_seconds"] == 120
    source = runtime.db.get(SourceVideo, body["source_video"]["id"])
    path = source_uploads.source_upload_path(runtime.user.id, source.original_url)
    assert path.read_bytes() == b"synthetic source"
    assert path.is_relative_to((jobs.settings.data_path / "users" / str(runtime.user.id)).resolve())
    assert not source_uploads.source_upload_path(runtime.user.id + 1, source.original_url).exists()
    job = runtime.db.get(Job, body["id"])
    job.status = "failed"
    runtime.db.commit()
    retry = runtime.client.post(f"/api/jobs/{job.id}/retry")
    assert retry.status_code == 202, retry.text
    assert retry.json()["id"] != job.id
    assert path.exists()
    assert runtime.db.get(Job, job.id).status == "failed"


@pytest.mark.parametrize("content,filename,rights,clips,code", [
    (b"data", "video.exe", "true", "1", 415),
    (b"", "video.mp4", "true", "1", 400),
    (b"data", "video.mp4", "false", "1", 400),
    (b"data", "video.mp4", "true", "11", 422),
])
def test_invalid_upload_never_creates_jobs(runtime, content, filename, rights, clips, code):
    response = submit(runtime, content, filename, rights, clips)
    assert response.status_code == code, response.text
    assert runtime.db.query(Job).count() == 0
    assert runtime.db.query(SourceVideo).count() == 0
    assert not list(jobs.settings.data_path.rglob("source.*"))


def test_upload_size_and_media_validation_cleanup(runtime, monkeypatch):
    monkeypatch.setattr(jobs, "MAX_UPLOAD_BYTES", 4)
    assert submit(runtime).status_code == 413
    monkeypatch.setattr(jobs, "MAX_UPLOAD_BYTES", 500 * 1024 * 1024)
    def invalid(_):
        raise ValueError("Arquivo inválido")
    monkeypatch.setattr(jobs, "inspect_uploaded_video", invalid)
    assert submit(runtime).status_code == 415
    assert runtime.db.query(Job).count() == 0
    assert not list(jobs.settings.data_path.rglob("source.*"))


def test_plan_limits_apply_to_uploaded_video_duration(runtime, monkeypatch):
    runtime.user.role = "member"
    observed = []
    monkeypatch.setattr(jobs, "ensure_plan", lambda *_: object())
    def limits(_db, _plan, duration, clips):
        observed.append((duration, clips))
        return False, "Limite de minutos excedido"
    monkeypatch.setattr(jobs, "can_create_job", limits)
    assert submit(runtime, clips="5").status_code == 402
    assert observed == [(120, 5)]
    assert runtime.db.query(Job).count() == 0
    assert not list(jobs.settings.data_path.rglob("source.*"))


def test_upload_requires_login(runtime):
    runtime.app.dependency_overrides.pop(get_current_user)
    assert submit(runtime).status_code == 401
    assert runtime.db.query(Job).count() == 0


@pytest.mark.parametrize("reference", ["upload:///etc/passwd", "upload://../source.mp4", "upload://" + "a" * 32 + "/../../secret.mp4"])
def test_source_reference_rejects_path_traversal(reference):
    with pytest.raises(ValueError):
        source_uploads.source_upload_path(1, reference)


def test_real_video_reaches_render_without_any_youtube_download(runtime, monkeypatch):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required for real media verification")
    media = runtime.root / "fixture.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=320x240:r=25", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000", "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(media)], check=True, capture_output=True)
    monkeypatch.setattr(jobs, "inspect_uploaded_video", source_uploads.inspect_uploaded_video)
    response = submit(runtime, media.read_bytes(), clips="1")
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    monkeypatch.setattr(pipeline, "download_video", lambda *_args, **_kwargs: pytest.fail("Uploaded media must never contact YouTube"))
    monkeypatch.setattr(pipeline, "transcribe_chunks", lambda *_args, **_kwargs: ("Conteúdo de teste para criar um corte.", [{"start": 0, "end": 1.5, "text": "Conteúdo de teste para criar um corte."}]))
    monkeypatch.setattr(pipeline, "select_clips", lambda *_args: [SimpleNamespace(start=0, end=1.5, hook="Conteúdo de teste", reason="test", title="Teste do servidor", description="Teste", tags=["teste"], copy="Teste")])
    pipeline.run_pipeline(job_id)
    runtime.db.expire_all()
    job = runtime.db.get(Job, job_id)
    assert job.status == "ready_for_review", job.error
    assert len(job.clips) == 1
    from pathlib import Path
    output = Path(job.clips[0].file_path)
    assert output.is_file() and output.stat().st_size > 0
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(output)], capture_output=True, text=True, check=True)
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["width"] * 16 == stream["height"] * 9
