from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Clip, User
from ..schemas import ClipOut, UploadRequest
from ..services.serializers import clip_to_dict
from ..services.youtube_oauth import get_connection_status

router = APIRouter(prefix="/clips", tags=["clips"])


@router.get("", response_model=list[ClipOut])
def list_clips(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    clips = db.query(Clip).filter(Clip.user_id == user.id).order_by(Clip.id.desc()).limit(100).all()
    return [clip_to_dict(clip) for clip in clips]


@router.post("/{clip_id}/approve", response_model=ClipOut)
def approve_clip(clip_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    clip = db.query(Clip).filter(Clip.id == clip_id, Clip.user_id == user.id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Corte não encontrado para este perfil.")
    if clip.status == "uploaded":
        return clip_to_dict(clip)
    if clip.status in {"uploading", "upload_queued"}:
        raise HTTPException(status_code=409, detail="Este corte já está na fila ou sendo enviado.")
    clip.status = "approved"
    clip.upload_error = None
    db.commit()
    db.refresh(clip)
    return clip_to_dict(clip)


@router.post("/{clip_id}/upload", response_model=ClipOut, status_code=status.HTTP_202_ACCEPTED)
def upload_clip(
    clip_id: int,
    payload: UploadRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    clip = db.query(Clip).filter(Clip.id == clip_id, Clip.user_id == user.id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Corte não encontrado para este perfil.")
    if clip.status != "approved":
        raise HTTPException(status_code=409, detail="Aprove o corte antes de enviar.")
    if not get_connection_status(db, user.id)["connected"]:
        raise HTTPException(status_code=409, detail="Conecte o YouTube deste perfil antes de publicar.")
    clip.status = "upload_queued"
    clip.upload_privacy = payload.privacy_status
    clip.upload_error = None
    db.commit()
    db.refresh(clip)
    return clip_to_dict(clip)
