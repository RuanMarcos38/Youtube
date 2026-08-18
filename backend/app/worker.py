import time
from datetime import datetime, timezone
from .config import settings
from .database import Base, SessionLocal, engine
from .models import Clip, Job
from .services.pipeline import run_pipeline
from .services.upload_task import run_upload

PROCESSING_STATES = {"checking_ffmpeg", "downloading", "extracting_audio", "transcribing", "selecting_clips", "rendering"}
HEARTBEAT_FILE = settings.data_path / "worker_heartbeat.txt"


def _heartbeat() -> None:
    HEARTBEAT_FILE.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")


def _recover_interrupted() -> None:
    db = SessionLocal()
    try:
        for job in db.query(Job).filter(Job.status.in_(PROCESSING_STATES)).all():
            job.status = "queued"
            job.progress = 0
            job.error = "Recovered after worker restart"
        for clip in db.query(Clip).filter(Clip.status == "uploading").all():
            clip.status = "upload_queued"
            clip.upload_error = "Recovered after worker restart"
        db.commit()
    finally:
        db.close()


def _next_job_id() -> int | None:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.status == "queued").order_by(Job.id.asc()).first()
        return job.id if job else None
    finally:
        db.close()


def _next_upload() -> tuple[int, str] | None:
    db = SessionLocal()
    try:
        clip = db.query(Clip).filter(Clip.status == "upload_queued").order_by(Clip.id.asc()).first()
        if not clip:
            return None
        return clip.id, clip.upload_privacy or "private"
    finally:
        db.close()


def main() -> None:
    Base.metadata.create_all(bind=engine)
    settings.data_path.mkdir(parents=True, exist_ok=True)
    _recover_interrupted()
    while True:
        _heartbeat()
        job_id = _next_job_id()
        if job_id is not None:
            run_pipeline(job_id)
            continue
        upload = _next_upload()
        if upload is not None:
            run_upload(upload[0], upload[1])
            continue
        time.sleep(max(0.5, settings.worker_poll_seconds))


if __name__ == "__main__":
    main()
