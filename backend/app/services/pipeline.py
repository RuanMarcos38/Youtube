import json
from sqlalchemy.orm import joinedload
from ..database import SessionLocal
from ..models import Clip, Job
from ..config import settings
from .ai_service import select_clips
from .downloader import download_video
from .ffmpeg_service import ensure_ffmpeg, extract_audio_chunks, get_duration, render_vertical_clip, write_clip_srt
from .transcription import transcribe_chunks


def _set_status(job_id: int, status: str, progress: int, error: str | None = None) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        job.status = status
        job.progress = max(0, min(100, int(progress)))
        job.error = error
        db.commit()
    finally:
        db.close()


def _download_progress_updater(job_id: int):
    last_progress = 15

    def update(event: dict) -> None:
        nonlocal last_progress
        status = str(event.get("status") or "")
        next_progress = last_progress

        if status == "downloading":
            downloaded = event.get("downloaded_bytes") or 0
            total = event.get("total_bytes") or event.get("total_bytes_estimate") or 0
            if total and downloaded:
                ratio = max(0.0, min(1.0, float(downloaded) / float(total)))
                next_progress = 15 + int(ratio * 13)
            elif downloaded:
                # Show liveness even when YouTube does not expose a total size.
                next_progress = min(27, last_progress + 1)
        elif status == "finished":
            next_progress = 29

        if next_progress > last_progress:
            last_progress = next_progress
            _set_status(job_id, "downloading", next_progress)

    return update


def run_pipeline(job_id: int) -> None:
    db = SessionLocal()
    try:
        job = db.query(Job).options(joinedload(Job.source_video), joinedload(Job.clips)).filter(Job.id == job_id).first()
        if not job:
            return
        source = job.source_video
        for existing_clip in list(job.clips):
            db.delete(existing_clip)
        db.commit()
        work_dir = settings.data_path / "jobs" / str(job_id)
        work_dir.mkdir(parents=True, exist_ok=True)

        _set_status(job_id, "checking_ffmpeg", 5)
        ensure_ffmpeg()

        _set_status(job_id, "downloading", 15)
        video_path = download_video(
            source.original_url,
            work_dir,
            progress_hook=_download_progress_updater(job_id),
        )

        _set_status(job_id, "extracting_audio", 30)
        duration = get_duration(video_path)
        audio_files = extract_audio_chunks(video_path, work_dir / "audio")

        _set_status(job_id, "transcribing", 45)
        transcript_text, segments = transcribe_chunks(audio_files)
        (work_dir / "transcript.txt").write_text(transcript_text, encoding="utf-8")
        (work_dir / "segments.json").write_text(json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8")

        _set_status(job_id, "selecting_clips", 65)
        plan = select_clips(segments, duration, job.requested_clips, source.title)

        _set_status(job_id, "rendering", 75)
        total_clips = max(1, len(plan))
        for index, candidate in enumerate(plan, start=1):
            srt_path = work_dir / f"clip_{index:02d}.srt"
            output_path = work_dir / f"clip_{index:02d}.mp4"
            write_clip_srt(segments, candidate.start, candidate.end, srt_path)
            render_vertical_clip(video_path, output_path, candidate.start, candidate.end, srt_path)
            clip = Clip(
                job_id=job.id,
                start_seconds=candidate.start,
                end_seconds=candidate.end,
                hook=candidate.hook,
                reason=candidate.reason,
                title=candidate.title,
                description=candidate.description,
                copy_text=candidate.copy,
                tags_json=json.dumps(candidate.tags, ensure_ascii=False),
                file_path=str(output_path.resolve()),
                subtitle_path=str(srt_path.resolve()),
                status="ready",
            )
            db.add(clip)
            db.commit()
            render_progress = 75 + int((index / total_clips) * 24)
            _set_status(job_id, "rendering", min(99, render_progress))

        _set_status(job_id, "ready_for_review", 100)
    except Exception as exc:
        db.rollback()
        _set_status(job_id, "failed", 100, str(exc))
    finally:
        db.close()
