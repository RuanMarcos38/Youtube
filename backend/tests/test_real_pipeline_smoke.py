"""Actual FFmpeg + database + pipeline smoke test with a local owned-media fixture.

This is deliberately not a YouTube network test: remote extraction can be
blocked independently by YouTube authentication and source IP policy.
"""
import json
import shutil
import subprocess

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Clip, Job, SourceVideo, Tenant, User
from app.services import pipeline, ffmpeg_service
from app.services.local_uploads import source_reference, upload_path


@pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg tools are required for real rendering smoke test",
)
def test_uploaded_video_produces_real_vertical_mp4(tmp_path, monkeypatch):
    """Use actual video/audio decoding, local clip planning and 9:16 rendering."""
    monkeypatch.setattr(pipeline.settings, "data_dir", str(tmp_path / "data"))
    monkeypatch.setattr(pipeline.settings, "clip_planning_provider", "local")
    monkeypatch.setattr(ffmpeg_service.settings, "ffmpeg_preset", "ultrafast")
    monkeypatch.setattr(ffmpeg_service.settings, "ffmpeg_threads_per_job", 1)

    engine = create_engine(f"sqlite:///{tmp_path / 'smoke.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(pipeline, "SessionLocal", session_factory)
    monkeypatch.setattr(pipeline, "transcribe_chunks", lambda *_a, **_kw: (
        " ".join(f"Dica de marketing com conteúdo original etapa {i}." for i in range(8)),
        [
            {
                "start": float(i * 3),
                "end": float(i * 3 + 2.8),
                "text": f"Dica importante de marketing digital e estratégias para clientes etapa {i}."
            }
            for i in range(8)
        ],
    ))

    with session_factory() as db:
        tenant = Tenant(name="Smoke test", billing_status="active")
        db.add(tenant)
        db.flush()
        user = User(
            tenant_id=tenant.id, email="smoke@example.com", password_hash="unused",
            display_name="Smoke", role="superadmin", active=True,
        )
        db.add(user)
        db.flush()
        user_id, tenant_id = user.id, tenant.id
        upload_id = "1" * 32
        source_file = upload_path(user_id, upload_id, ".mp4")
        source_file.parent.mkdir(parents=True, exist_ok=True)

        # Original synthetic 24-second video with an audio stream.
        subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=10",
                "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
                "-t", "24", "-c:v", "mpeg4", "-q:v", "12",
                "-c:a", "aac", "-shortest", str(source_file),
            ],
            check=True, capture_output=True, text=True, timeout=90,
        )
        source = SourceVideo(
            tenant_id=tenant_id, user_id=user_id, youtube_id=upload_id,
            title="Teste de vídeo original", channel_title="Arquivo autorizado",
            original_url=source_reference(upload_id, ".mp4"),
            thumbnail_url="", duration_seconds=24, rights_confirmed=True,
        )
        db.add(source)
        db.flush()
        job = Job(
            tenant_id=tenant_id, user_id=user_id, source_video_id=source.id,
            requested_clips=1, status="queued", progress=0,
        )
        db.add(job)
        db.commit()
        job_id = job.id

    pipeline.run_pipeline(job_id)

    with session_factory() as db:
        job = db.get(Job, job_id)
        assert job.status == "ready_for_review", job.error
        assert job.progress == 100
        clips = db.query(Clip).filter(Clip.job_id == job_id).all()
        assert len(clips) == 1
        clip = clips[0]
        assert clip.status == "ready"
        assert clip.title
        assert clip.file_path
        output = clip.file_path
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height",
         "-of", "json", output],
        capture_output=True, text=True, check=True, timeout=30,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert (stream["width"], stream["height"]) == (1080, 1920)
