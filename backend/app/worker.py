import time
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone

from .config import settings
from .database import SessionLocal
from .models import Clip, Job, TikTokPost
from .services.database_bootstrap import initialize_database
from .services.download_probe import run_and_store_download_probe
from .services.editor_ai import claim_next_editor_task, recover_interrupted_editor_tasks
from .services.editor_ai_runtime import run_claimed_editor_task
from .services.pipeline import run_pipeline
from .services.tiktok_upload_task import refresh_tiktok_post, run_tiktok_upload
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
DOWNLOAD_PROBE_INTERVAL_SECONDS = 15 * 60
TIKTOK_STATUS_INTERVAL_SECONDS = 15
TIKTOK_STATUS_BATCH_SIZE = 6
# TikTok allows at most 6 Direct Post initialization requests per minute for
# each user access token. Keep a small safety margin so a large batch such as
# 40 videos remains queued instead of being rejected by rate limiting.
TIKTOK_UPLOAD_MIN_INTERVAL_SECONDS = 11.0
MAX_PIPELINE_CONCURRENCY = 5


def _pipeline_concurrency() -> int:
    """Return the configured pipeline capacity, hard-capped at five videos."""
    return max(1, min(int(settings.worker_concurrency), MAX_PIPELINE_CONCURRENCY))


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
        for post in db.query(TikTokPost).filter(TikTokPost.status == "uploading").all():
            post.status = "queued"
            post.error = "Recovered after worker restart"
        # Legacy versions marked TikTok uploads as submitted immediately after
        # sending the file. Keep them eligible for authoritative status checks.
        for post in db.query(TikTokPost).filter(TikTokPost.status == "submitted", TikTokPost.publish_id.is_not(None)).all():
            post.status = "processing"
            post.error = "Aguardando confirmação final do TikTok."
        # A draft delivered to TikTok is not a completed post. Previous builds
        # stopped polling at draft_sent and hid the clip too early. Recover
        # those rows so they remain visible until TikTok says PUBLISH_COMPLETE.
        for post in db.query(TikTokPost).filter(TikTokPost.status == "draft_sent", TikTokPost.publish_id.is_not(None)).all():
            post.status = "processing"
            post.error = (
                "Rascunho entregue ao TikTok. Abra a notificação na Caixa de Entrada do aplicativo e conclua a publicação. "
                "O ShortsFlow continuará acompanhando este envio."
            )
        db.commit()
    finally:
        db.close()
    recover_interrupted_editor_tasks()


def _claim_next_job_id() -> int | None:
    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.status == "queued").order_by(Job.id.asc()).first()
        if not job:
            return None
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
        privacy = "public"
        clip.upload_privacy = privacy
        clip.status = "uploading"
        clip.upload_error = None
        db.commit()
        return clip.id, privacy
    finally:
        db.close()


def _claim_next_tiktok_post() -> int | None:
    db = SessionLocal()
    try:
        post = db.query(TikTokPost).filter(TikTokPost.status == "queued").order_by(TikTokPost.id.asc()).first()
        if not post:
            return None
        post.status = "uploading"
        post.error = None
        db.commit()
        return post.id
    finally:
        db.close()


def _tiktok_status_batch() -> list[int]:
    db = SessionLocal()
    try:
        rows = (
            db.query(TikTokPost)
            .filter(TikTokPost.status.in_(["processing", "submitted", "draft_sent"]), TikTokPost.publish_id.is_not(None))
            .order_by(TikTokPost.updated_at.asc(), TikTokPost.id.asc())
            .limit(TIKTOK_STATUS_BATCH_SIZE)
            .all()
        )
        return [row.id for row in rows]
    finally:
        db.close()


def _refresh_tiktok_batch(post_ids: list[int]) -> None:
    for post_id in post_ids:
        refresh_tiktok_post(post_id)


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
    settings.data_path.mkdir(parents=True, exist_ok=True)
    initialize_database()
    _recover_interrupted()

    concurrency = _pipeline_concurrency()
    active_jobs: dict[Future, int] = {}
    active_upload: Future | None = None
    active_tiktok_upload: Future | None = None
    active_probe: Future | None = None
    active_editor: Future | None = None
    last_probe_started = 0.0
    last_tiktok_status_started = 0.0
    last_tiktok_upload_started = 0.0

    with (
        ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="shortsflow-job") as job_pool,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="shortsflow-upload") as upload_pool,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="shortsflow-tiktok") as tiktok_pool,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="shortsflow-probe") as probe_pool,
        ThreadPoolExecutor(max_workers=1, thread_name_prefix="shortsflow-editor-ai") as editor_pool,
    ):
        while True:
            _heartbeat()
            _collect_finished_jobs(active_jobs)

            if active_upload is not None and active_upload.done():
                try:
                    active_upload.result()
                except Exception:
                    pass
                active_upload = None

            if active_tiktok_upload is not None and active_tiktok_upload.done():
                try:
                    active_tiktok_upload.result()
                except Exception:
                    pass
                active_tiktok_upload = None

            if active_probe is not None and active_probe.done():
                try:
                    active_probe.result()
                except Exception:
                    pass
                active_probe = None

            if active_editor is not None and active_editor.done():
                try:
                    active_editor.result()
                except Exception:
                    pass
                active_editor = None

            now = time.monotonic()
            if active_probe is None and (
                last_probe_started == 0.0 or now - last_probe_started >= DOWNLOAD_PROBE_INTERVAL_SECONDS
            ):
                last_probe_started = now
                active_probe = probe_pool.submit(run_and_store_download_probe)

            while len(active_jobs) < concurrency:
                job_id = _claim_next_job_id()
                if job_id is None:
                    break
                active_jobs[job_pool.submit(run_pipeline, job_id)] = job_id

            if active_upload is None:
                upload = _claim_next_upload()
                if upload is not None:
                    active_upload = upload_pool.submit(run_upload, upload[0], upload[1])

            if active_tiktok_upload is None:
                status_due = last_tiktok_status_started == 0.0 or now - last_tiktok_status_started >= TIKTOK_STATUS_INTERVAL_SECONDS
                status_ids = _tiktok_status_batch() if status_due else []
                if status_ids:
                    last_tiktok_status_started = now
                    active_tiktok_upload = tiktok_pool.submit(_refresh_tiktok_batch, status_ids)
                elif last_tiktok_upload_started == 0.0 or now - last_tiktok_upload_started >= TIKTOK_UPLOAD_MIN_INTERVAL_SECONDS:
                    post_id = _claim_next_tiktok_post()
                    if post_id is not None:
                        last_tiktok_upload_started = now
                        active_tiktok_upload = tiktok_pool.submit(run_tiktok_upload, post_id)

            if active_editor is None:
                editor_task = claim_next_editor_task()
                if editor_task is not None:
                    active_editor = editor_pool.submit(
                        run_claimed_editor_task,
                        editor_task[0],
                        editor_task[1],
                        editor_task[2],
                    )

            time.sleep(max(0.5, settings.worker_poll_seconds))


if __name__ == "__main__":
    main()
