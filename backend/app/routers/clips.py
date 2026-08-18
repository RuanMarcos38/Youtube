from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Clip
from ..schemas import ClipOut, UploadRequest
from ..services.serializers import clip_to_dict

router = APIRouter(prefix="/clips", tags=["clips"])


@router.get("", response_model=list[ClipOut])
def list_clips(db: Session = Depends(get_db)):
    clips = db.query(Clip).order_by(Clip.id.desc()).limit(100).all()
    return [clip_to_dict(clip) for clip in clips]


@router.post("/{clip_id}/approve", response_model=ClipOut)
def approve_clip(clip_id: int, db: Session = Depends(get_db)):
    clip = db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    if clip.status == "uploaded":
        return clip_to_dict(clip)
    if clip.status in {"uploading", "upload_queued"}:
        raise HTTPException(status_code=409, detail="Clip is already queued/uploading")
    clip.status = "approved"
    clip.upload_error = None
    db.commit()
    db.refresh(clip)
    return clip_to_dict(clip)


@router.post("/{clip_id}/upload", response_model=ClipOut, status_code=status.HTTP_202_ACCEPTED)
def upload_clip(clip_id: int, payload: UploadRequest, db: Session = Depends(get_db)):
    clip = db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    if clip.status != "approved":
        raise HTTPException(status_code=409, detail="Approve the clip before uploading")
    clip.status = "upload_queued"
    clip.upload_privacy = payload.privacy_status
    clip.upload_error = None
    db.commit()
    db.refresh(clip)
    return clip_to_dict(clip)
