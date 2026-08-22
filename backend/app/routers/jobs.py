from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from ..config import settings
from ..database import get_db
from ..models import Job, SourceVideo
from ..schemas import JobCreate, JobOut
from ..services.downloader import download_access_configured
from ..services.serializers import job_to_dict

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def create_job(payload: JobCreate, db: Session = Depends(get_db)):
    if not payload.rights_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirm that you own the source or have permission/license to download, edit and republish it.",
        )

    # The production VPS is challenged by YouTube when it runs as a guest.
    # Reject before creating a doomed job instead of showing 100%/Falhou later.
    if settings.environment.strip().lower() == "production" and not download_access_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "O download do YouTube ainda não está autenticado no servidor. "
                "Configure YTDLP_COOKIES_B64 ou YTDLP_PROXY_URL no serviço shortsia e faça o deploy."
            ),
        )

    source = db.query(SourceVideo).filter(SourceVideo.youtube_id == payload.video_id).first()
    if source is None:
        source = SourceVideo(
            youtube_id=payload.video_id,
            title=payload.title,
            channel_title=payload.channel_title,
            original_url=str(payload.url or f"https://www.youtube.com/watch?v={payload.video_id}"),
            thumbnail_url=payload.thumbnail_url,
            rights_confirmed=True,
        )
        db.add(source)
        db.flush()
    else:
        source.title = payload.title
        source.channel_title = payload.channel_title
        source.thumbnail_url = payload.thumbnail_url
        source.rights_confirmed = True

    job = Job(source_video_id=source.id, requested_clips=payload.requested_clips, status="queued", progress=0)
    db.add(job)
    db.commit()

    job = (
        db.query(Job)
        .options(joinedload(Job.source_video), joinedload(Job.clips))
        .filter(Job.id == job.id)
        .first()
    )
    return job_to_dict(job)


@router.get("", response_model=list[JobOut])
def list_jobs(db: Session = Depends(get_db)):
    jobs = (
        db.query(Job)
        .options(joinedload(Job.source_video), joinedload(Job.clips))
        .order_by(Job.id.desc())
        .limit(50)
        .all()
    )
    return [job_to_dict(job) for job in jobs]


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = (
        db.query(Job)
        .options(joinedload(Job.source_video), joinedload(Job.clips))
        .filter(Job.id == job_id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_to_dict(job)
