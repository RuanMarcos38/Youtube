from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Clip, User
from ..schemas import ClipCaptionUpdateRequest, ClipOut, UploadRequest
from ..services.ffmpeg_service import FFmpegError, ensure_ffmpeg, render_vertical_clip
from ..services.serializers import clip_to_dict
from ..services.youtube_oauth import get_connection_status

router = APIRouter(prefix="/clips", tags=["clips"])


@router.get("", response_model=list[ClipOut])
def list_clips(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    clips = (
        db.query(Clip)
        .filter(Clip.user_id == user.id, Clip.status != "uploaded")
        .order_by(Clip.id.desc())
        .limit(100)
        .all()
    )
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


def _srt_timestamp(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def _normalize_subtitle_text(value: str, duration: float) -> str:
    text = value.strip()
    if not text:
        return ""
    if "-->" in text:
        return text.rstrip() + "\n"
    return f"1\n00:00:00,000 --> {_srt_timestamp(duration)}\n{text}\n"


def _source_path_for_clip(clip: Clip) -> Path | None:
    output_path = Path(clip.file_path)
    work_dir = output_path.parent
    for extension in (".mp4", ".mkv", ".webm", ".mov"):
        source = work_dir / f"source{extension}"
        if source.is_file():
            return source
    for source in sorted(work_dir.glob("source.*")):
        if source.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"} and source.is_file():
            return source
    return None


@router.patch("/{clip_id}/captions", response_model=ClipOut)
def update_clip_captions(
    clip_id: int,
    payload: ClipCaptionUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    clip = db.query(Clip).filter(Clip.id == clip_id, Clip.user_id == user.id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Corte não encontrado para este perfil.")
    if clip.status in {"upload_queued", "uploading"}:
        raise HTTPException(status_code=409, detail="Aguarde o envio atual terminar antes de ajustar a legenda.")
    if clip.status == "uploaded":
        raise HTTPException(status_code=409, detail="Este corte já foi publicado. Ajuste a legenda antes de enviar ao YouTube.")

    source_path = _source_path_for_clip(clip)
    output_path = Path(clip.file_path)
    if not source_path:
        raise HTTPException(status_code=409, detail="Arquivo original do processamento não encontrado para recriar a legenda.")
    if not output_path.parent.is_dir():
        raise HTTPException(status_code=409, detail="Pasta do corte não encontrada no servidor.")

    subtitle_path = Path(clip.subtitle_path) if clip.subtitle_path else output_path.with_suffix(".srt")
    subtitle_path.parent.mkdir(parents=True, exist_ok=True)
    if payload.subtitle_srt is not None:
        duration = max(0.1, clip.end_seconds - clip.start_seconds)
        subtitle_path.write_text(_normalize_subtitle_text(payload.subtitle_srt, duration), encoding="utf-8")
        clip.subtitle_path = str(subtitle_path.resolve())

    temporary_output = output_path.with_name(f"{output_path.stem}.legenda-tmp{output_path.suffix}")
    try:
        ensure_ffmpeg()
        render_vertical_clip(
            source_path,
            temporary_output,
            clip.start_seconds,
            clip.end_seconds,
            subtitle_path,
            caption_position=payload.caption_position,
            caption_margin_v=payload.caption_margin_v,
            caption_font_size=payload.caption_font_size,
        )
        temporary_output.replace(output_path)
    except FFmpegError as exc:
        temporary_output.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Falha ao recriar a legenda: {exc}") from exc
    except OSError as exc:
        temporary_output.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="Falha ao substituir o vídeo renderizado com a nova legenda.") from exc

    clip.caption_position = payload.caption_position
    clip.caption_margin_v = payload.caption_margin_v
    clip.caption_font_size = payload.caption_font_size
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
