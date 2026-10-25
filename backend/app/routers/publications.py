from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..auth import get_current_user
from ..database import get_db
from ..config import settings
from ..errors import YouTubeAuthError
from ..models import Clip, SystemSetting, TikTokPost, User
from ..services.database_bootstrap import PUBLICATIONS_RESET_KEY
from ..services.serializers import clip_to_dict
from ..services.tiktok_policy import recover_retryable_draft_uploads
from ..services.youtube_upload import delete_video
from ..services.youtube_upload_availability import upload_availability


router = APIRouter(prefix="/publications", tags=["publications"])


class LocalCleanupRequest(BaseModel):
    confirmed: bool = False


@router.post("/youtube/{clip_id}/clean-local-files")
def clean_local_files(
    clip_id: int,
    payload: LocalCleanupRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    clip = db.query(Clip).filter(Clip.id == clip_id, Clip.user_id == user.id).with_for_update().first()
    if not clip:
        raise HTTPException(status_code=404, detail="Publicação não encontrada para este perfil.")
    if not payload.confirmed:
        raise HTTPException(status_code=400, detail="Confirme a remoção permanente dos arquivos locais.")
    if clip.status != "uploaded" or not (clip.youtube_video_id or "").strip():
        raise HTTPException(status_code=409, detail="A limpeza exige publicação confirmada no YouTube.")
    post = db.query(TikTokPost).filter(TikTokPost.clip_id == clip.id).first()
    if post and post.status != "published":
        raise HTTPException(status_code=409, detail="Conclua ou cancele o envio ao TikTok antes de limpar este arquivo.")

    # Only the exact rendered video and subtitle in this user's job directory.
    # Never recursively remove a directory, source video, or another project.
    root = settings.data_path.resolve()
    expected = root / "users" / str(user.id) / "jobs" / str(clip.job_id)
    paths = []
    for value in (clip.file_path, clip.subtitle_path):
        if not value:
            continue
        path = Path(value)
        if path.is_symlink() or path.resolve().parent != expected or expected.resolve() != expected:
            raise HTTPException(status_code=409, detail="Arquivo fora da pasta segura deste processamento.")
        if path.name.startswith("source.") or path.suffix.lower() not in {".mp4", ".srt"}:
            raise HTTPException(status_code=409, detail="Este arquivo não é um corte ou legenda removível.")
        # Do not remove a shared artifact referenced by another clip.
        shared = db.query(Clip).filter(Clip.id != clip.id, (Clip.file_path == value) | (Clip.subtitle_path == value)).first()
        if shared:
            raise HTTPException(status_code=409, detail="Arquivo compartilhado com outro corte; limpeza bloqueada.")
        paths.append(path)
    removed = 0
    freed_bytes = 0
    try:
        for path in set(paths):
            if path.is_file():
                size = path.stat().st_size
                path.unlink()
                removed += 1
                freed_bytes += size
    except OSError as exc:
        raise HTTPException(status_code=409, detail="Não foi possível concluir a limpeza. Tente novamente.") from exc
    clip.file_path = ""
    clip.subtitle_path = ""
    db.commit()
    return {"ok": True, "clip_id": clip.id, "removed_files": removed, "freed_bytes": freed_bytes}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _reset_at(user: User, db: Session) -> datetime | None:
    if user.role != "superadmin":
        return None
    marker = db.get(SystemSetting, PUBLICATIONS_RESET_KEY)
    if not marker or not marker.value:
        return None
    try:
        return _utc(datetime.fromisoformat(marker.value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _base_clips(user: User, db: Session) -> list[Clip]:
    rows = (
        db.query(Clip)
        .filter(Clip.user_id == user.id)
        .order_by(Clip.id.desc())
        .limit(200)
        .all()
    )
    reset = _reset_at(user, db)
    if reset is not None:
        rows = [row for row in rows if _utc(row.created_at) >= reset]
    return rows


@router.get("/youtube")
def youtube_publications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the YouTube queue independently from the TikTok queue."""
    rows = [clip for clip in _base_clips(user, db) if clip.status not in {"uploaded", "archived"}]
    return {
        "platform": "youtube",
        "availability": upload_availability(db, user.id),
        "clips": [clip_to_dict(clip) for clip in rows],
    }


@router.get("/youtube/history")
def youtube_publication_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return only videos that ShortsFlow confirmed as published on YouTube."""
    rows = [
        clip
        for clip in _base_clips(user, db)
        if clip.status == "uploaded" and bool((clip.youtube_video_id or "").strip())
    ]
    return {
        "platform": "youtube",
        "clips": [{**clip_to_dict(clip), "local_files_cleaned": not bool(clip.file_path)} for clip in rows],
    }


@router.delete("/youtube/{clip_id}")
def delete_youtube_publication(
    clip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a published Short from YouTube and remove it from ShortsFlow.

    The local record is archived only after YouTube confirms deletion (or says
    the video no longer exists). Credentials and OAuth secrets are never
    changed by this operation.
    """
    clip = db.query(Clip).filter(Clip.id == clip_id, Clip.user_id == user.id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Publicação não encontrada para este perfil.")
    if clip.status != "uploaded" or not (clip.youtube_video_id or "").strip():
        raise HTTPException(status_code=409, detail="Este Short não possui uma publicação confirmada no YouTube para excluir.")

    video_id = str(clip.youtube_video_id).strip()
    try:
        result = delete_video(video_id, user.id)
    except YouTubeAuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=f"Não foi possível excluir o vídeo no YouTube: {exc}") from exc

    # Preserve the database row only as an internal audit reference while
    # removing it from every normal ShortsFlow publication/review listing.
    # The remote YouTube id remains stored for traceability and is never reused.
    clip.status = "archived"
    clip.upload_error = None
    db.commit()

    return {
        "ok": True,
        "clip_id": clip.id,
        "youtube_video_id": video_id,
        "already_missing": bool(result.get("already_missing")),
    }


@router.get("/tiktok")
def tiktok_publications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Return the same generated Shorts for TikTok without sharing YouTube status.

    No video file is duplicated on disk: both platform tabs reference the same
    rendered Short while keeping publication state independent. A TikTok item
    is removed only after TikTok confirms PUBLISH_COMPLETE with a public post
    id. Inbox/draft delivery is not treated as a completed publication.
    """
    recover_retryable_draft_uploads(db, user_id=user.id)
    clips = [clip for clip in _base_clips(user, db) if clip.status != "archived" and clip.file_path]
    ids = [clip.id for clip in clips]
    posts = {
        post.clip_id: post
        for post in (
            db.query(TikTokPost)
            .filter(TikTokPost.user_id == user.id, TikTokPost.clip_id.in_(ids))
            .all()
            if ids
            else []
        )
    }
    items = []
    for clip in clips:
        post = posts.get(clip.id)
        if post and post.status == "published":
            continue
        payload = clip_to_dict(clip)
        payload["tiktok_status"] = post.status if post else "ready"
        payload["tiktok_error"] = post.error if post else None
        payload["tiktok_publish_id"] = post.publish_id if post else None
        items.append(payload)
    return {"platform": "tiktok", "clips": items}


@router.get("/tiktok/history")
def tiktok_publication_history(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(TikTokPost)
        .filter(TikTokPost.user_id == user.id)
        .order_by(TikTokPost.updated_at.desc(), TikTokPost.id.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": row.id,
            "clip_id": row.clip_id,
            "status": row.status,
            "publish_id": row.publish_id,
            "privacy_level": row.privacy_level,
            "error": row.error,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]
