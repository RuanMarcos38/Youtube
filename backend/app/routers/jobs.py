import shutil

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Job, SourceVideo, SystemSetting, User
from ..schemas import JobCreate, JobOut
from ..services.billing import can_use_tool, ensure_plan
from ..services.downloader import download_access_configured
from ..services.plans import can_create_job
from ..services.serializers import job_to_dict
from ..services.youtube_search import get_video_duration_seconds
from ..services.residential_proxy import connection_status as residential_status
from ..services.runtime_download_auth import permanent_proxy_url
from .system import _worker_alive

router = APIRouter(prefix="/jobs", tags=["jobs"])

HIDDEN_PROCESSING_STATUSES = ("ready_for_review",)


def _ensure_job_can_be_queued(user: User, db: Session, duration_seconds: int, requested_clips: int) -> None:
    allowed, reason = can_use_tool(db, user)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)

    if user.role != "superadmin":
        plan = ensure_plan(db, user.tenant_id)
        allowed, reason = can_create_job(db, plan, duration_seconds, requested_clips)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)

    if settings.environment.strip().lower() == "production" and not download_access_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O download do YouTube ainda não está autenticado no servidor. O administrador precisa renovar a sessão de download.",
        )


def _create_queued_job(db: Session, user: User, source: SourceVideo, requested_clips: int, *, retry_key: str | None = None) -> dict:
    source.rights_confirmed = True
    job = Job(
        tenant_id=user.tenant_id,
        user_id=user.id,
        source_video_id=source.id,
        requested_clips=max(1, min(10, requested_clips)),
        status="queued",
        progress=0,
    )
    db.add(job)
    if retry_key:
        db.flush()
        db.add(SystemSetting(key=retry_key, value=str(job.id), secret=False))
    db.commit()
    job_id = job.id

    job = (
        db.query(Job)
        .options(joinedload(Job.source_video), joinedload(Job.clips))
        .filter(Job.id == job_id, Job.user_id == user.id, Job.tenant_id == user.tenant_id)
        .first()
    )
    return job_to_dict(job)


def _remove_failed_job(db: Session, user_id: int, job: Job) -> None:
    work_dir = settings.data_path / "users" / str(user_id) / "jobs" / str(job.id)
    db.delete(job)
    db.commit()
    shutil.rmtree(work_dir, ignore_errors=True)


def _validated_duration(payload: JobCreate, source: SourceVideo | None) -> int:
    if payload.duration_seconds > 0:
        return payload.duration_seconds
    if source and source.duration_seconds > 0:
        return source.duration_seconds
    try:
        duration = get_video_duration_seconds(payload.video_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível validar a duração do vídeo para aplicar o limite do plano. Tente novamente.",
        ) from exc
    if duration <= 0:
        raise HTTPException(status_code=409, detail="A duração do vídeo não pôde ser identificada.")
    return duration


@router.post("", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def create_job(payload: JobCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not payload.rights_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirme que você possui direitos, licença ou autorização para reutilizar o conteúdo.",
        )

    source = (
        db.query(SourceVideo)
        .filter(SourceVideo.user_id == user.id, SourceVideo.youtube_id == payload.video_id)
        .first()
    )
    duration_seconds = _validated_duration(payload, source)
    _ensure_job_can_be_queued(user, db, duration_seconds, payload.requested_clips)

    if source is None:
        source = SourceVideo(
            tenant_id=user.tenant_id,
            user_id=user.id,
            youtube_id=payload.video_id,
            title=payload.title,
            channel_title=payload.channel_title,
            original_url=str(payload.url or f"https://www.youtube.com/watch?v={payload.video_id}"),
            thumbnail_url=payload.thumbnail_url,
            duration_seconds=duration_seconds,
            rights_confirmed=True,
        )
        db.add(source)
        db.flush()
    else:
        source.title = payload.title
        source.channel_title = payload.channel_title
        source.thumbnail_url = payload.thumbnail_url
        source.duration_seconds = duration_seconds
        source.rights_confirmed = True

    return _create_queued_job(db, user, source, payload.requested_clips)


@router.get("", response_model=list[JobOut])
def list_jobs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    jobs = (
        db.query(Job)
        .options(joinedload(Job.source_video), joinedload(Job.clips))
        .filter(Job.user_id == user.id, Job.status.notin_(HIDDEN_PROCESSING_STATUSES))
        .order_by(Job.id.desc())
        .limit(50)
        .all()
    )
    return [job_to_dict(job) for job in jobs]


@router.post("/{job_id}/retry", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def retry_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    original = (
        db.query(Job)
        .options(joinedload(Job.source_video), joinedload(Job.clips))
        .filter(Job.id == job_id, Job.tenant_id == user.tenant_id)
        .first()
    )
    if not original:
        raise HTTPException(status_code=404, detail="Processamento não encontrado. Atualize a fila.")
    if original.user_id != user.id:
        raise HTTPException(status_code=403, detail="Você não tem permissão para reenviar este processamento.")
    if original.status != "failed":
        raise HTTPException(status_code=409, detail="Apenas processamentos falhados podem ser reenviados.")
    if not original.source_video:
        raise HTTPException(status_code=409, detail="O vídeo de origem deste processamento não foi encontrado.")
    if original.source_video.user_id != user.id or original.source_video.tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="O vídeo de origem não pertence a este perfil.")

    # Jobs criados antes do controle por minutos não possuem duração persistida.
    # Preserve o comportamento de reenvio existente sem criar uma dependência
    # nova da API do YouTube. Eles continuam sujeitos ao limite de Shorts, mas
    # não são cobrados retroativamente em minutos.
    duration_seconds = max(0, int(original.source_video.duration_seconds or 0))

    # Serialize retries of this source in both PostgreSQL and SQLite. The
    # no-op write holds a lock until the new attempt is committed.
    db.query(SourceVideo).filter(SourceVideo.id == original.source_video_id, SourceVideo.user_id == user.id,
                                 SourceVideo.tenant_id == user.tenant_id).update(
        {SourceVideo.rights_confirmed: SourceVideo.rights_confirmed}, synchronize_session=False,
    )
    # Persist the retry relationship in the existing settings table, in the same
    # transaction as the new job. No schema change or deletion is needed.
    retry_key = f"job_retry:{user.tenant_id}:{user.id}:{job_id}"
    attempt = db.get(SystemSetting, retry_key)
    if attempt:
        retried = db.query(Job).options(joinedload(Job.source_video), joinedload(Job.clips)).filter(
            Job.id == int(attempt.value), Job.user_id == user.id, Job.tenant_id == user.tenant_id,
        ).first()
        if not retried:
            db.rollback()
            raise HTTPException(status_code=409, detail="A tentativa vinculada foi excluída. Atualize a fila antes de continuar.")
        result = job_to_dict(retried)
        db.commit()
        return result
    active = (
        db.query(Job).options(joinedload(Job.source_video), joinedload(Job.clips))
        .filter(Job.user_id == user.id, Job.tenant_id == user.tenant_id, Job.source_video_id == original.source_video_id,
                Job.status.notin_(("failed", "ready_for_review")))
        .order_by(Job.id.desc()).first()
    )
    if active:
        result = job_to_dict(active)
        db.add(SystemSetting(key=retry_key, value=str(active.id), secret=False))
        db.commit()
        return result
    if settings.environment.strip().lower() == "production":
        if not _worker_alive():
            db.rollback()
            raise HTTPException(status_code=503, detail="O worker de vídeo está indisponível. Aguarde e tente novamente.")
        residential = residential_status(settings.data_path)
        if residential["enabled"] and not residential["connected"] and not permanent_proxy_url():
            db.rollback()
            raise HTTPException(status_code=503, detail="A conexão residencial está offline. Abra o cliente no computador e reconecte antes de tentar novamente. Nenhuma nova tentativa foi criada.")
    _ensure_job_can_be_queued(user, db, duration_seconds, original.requested_clips)
    # Keep the failed attempt and its partial media as history.
    return _create_queued_job(db, user, original.source_video, original.requested_clips, retry_key=retry_key)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_failed_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = (
        db.query(Job)
        .options(joinedload(Job.clips))
        .filter(Job.id == job_id, Job.user_id == user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado para este perfil.")
    if job.status != "failed":
        raise HTTPException(status_code=409, detail="Apenas processamentos que falharam podem ser excluídos.")

    _remove_failed_job(db, user.id, job)
    return None


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = (
        db.query(Job)
        .options(joinedload(Job.source_video), joinedload(Job.clips))
        .filter(Job.id == job_id, Job.user_id == user.id)
        .first()
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado para este perfil.")
    return job_to_dict(job)
