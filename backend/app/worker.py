import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone

from .config import settings
from .database import Base, SessionLocal, engine
from .models import Clip, Job
from .services.pipeline import run_pipeline
from .services.upload_task import run_upload

PROCESSING_STATES = {
    "checking_ffmpeg",
    "downloading",
    "extracting_audio",
    "transcribing",
    "selecting_clips",
    "rendering",
}
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


def _claim_next_job_id() -> int | None:
    """Claim one queued job before dispatching it to a worker thread."""
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.status == "queued").order_by(Job.id.asc()).first()
        if not job:
            return None
        # Reuse an existing frontend status while claiming, so the UI shows
        # "Preparando" instead of an unknown internal status.
        job.status = "checking_ffmpeg"
        job.progress = max(1, job.progress or 0)
        job.error = None
        db.commit()
        return job.id
    finally:
        db.close()


def _claim_next_upload() -> tuple[int, str] | None:
    db = SessionLocal()
    try:
        clip = db.query(Clip).filter(Clip.status == "upload_queued").order_by(Clip.id.asc()).first()
        if not clip:
            return None
        privacy = clip.upload_privacy or "private"
        clip.status = "uploading"
        clip.upload_error = None
        db.commit()
        return clip.id, privacy
    finally:
        db.close()


def _collect_finished_jobs(active: dict[Future, int]) -> None:
    for future, job_id in list(active.items()):
        if not future.done():
            continue
        try:
            future.result()
        except Exception as exc:
            db = SessionLocal()
            try:
                job = db.get(Job, job_id)
                if job and job.status not in {"failed", "ready_for_review"}:
                    job.status = "failed"
                    job.progress = 100
                    job.error = f"Worker failure: {exc}"
                    db.commit()
            finally:
                db.close()
        active.pop(future, None)


def main() -> None:
    Base.metadata.create_all(bind=engine)
    settings.data_path.mkdir(parents=True, exist_ok=True)
    _recover_interrupted()

    concurrency = max(1, min(int(settings.worker_concurrency), 4))
    active_jobs: dict[Future, int] = {}
    active_upload: Future | None = None

    # The dispatcher stays alive while heavy pipeline work runs in background
    # threads. This keeps /api/health alive and prevents a single long download
    # from freezing every subsequent video in the queue.
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="shortsflow-job") as job_pool, ThreadPoolExecutor(
        max_workers=1,
        thread_name_prefix="shortsflow-upload",
    ) as upload_pool:
        while True:
            _heartbeat()
            _collect_finished_jobs(active_jobs)

            if active_upload is not None and active_upload.done():
                try:
                    active_upload.result()
                except Exception:
                    pass
                active_upload = None

            while len(active_jobs) < concurrency:
                job_id = _claim_next_job_id()
                if job_id is None:
                    break
                active_jobs[job_pool.submit(run_pipeline, job_id)] = job_id

            if active_upload is None:
                upload = _claim_next_upload()
                if upload is not None:
                    active_upload = upload_pool.submit(run_upload, upload[0], upload[1])

            time.sleep(max(0.5, settings.worker_poll_seconds))


if __name__ == "__main__":
    main()
