from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import Clip, TikTokPost, User


router = APIRouter(prefix="/clips", tags=["clips"])

# A exclusão local é propositalmente restrita a cortes que ainda não entraram
# em uma publicação. Isso evita remover um arquivo enquanto YouTube/TikTok ainda
# o utilizam e preserva o fluxo existente da plataforma.
DELETE_ALLOWED_STATUSES = {"ready", "approved", "upload_failed"}


class BatchDeleteRequest(BaseModel):
    clip_ids: list[int] = Field(min_length=1, max_length=100)


class BatchDeleteResponse(BaseModel):
    deleted: int
    skipped: int
    clip_ids: list[int]


def _deletion_block_reason(clip: Clip, *, has_tiktok_post: bool) -> str | None:
    if (clip.youtube_video_id or "").strip() or clip.status == "uploaded":
        return "Este corte já possui publicação no YouTube e não pode ser removido por esta ação."
    if clip.status not in DELETE_ALLOWED_STATUSES:
        return "Este corte está em processamento ou em uma fila de publicação e não pode ser excluído agora."
    if has_tiktok_post:
        return "Este corte já possui histórico/fila no TikTok e foi protegido contra exclusão local."
    return None


def _file_paths(clip: Clip) -> list[Path]:
    paths: list[Path] = []
    for raw in (clip.file_path, clip.subtitle_path):
        value = (raw or "").strip()
        if not value:
            continue
        path = Path(value)
        if path not in paths:
            paths.append(path)
    return paths


def _cleanup_files(paths: list[Path]) -> None:
    # O registro é confirmado no banco antes da limpeza física. Se o disco
    # estiver temporariamente indisponível, a exclusão lógica continua íntegra
    # e nenhum diretório do job (que pode conter outros cortes) é apagado.
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


@router.delete("/{clip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_unpublished_clip(
    clip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    clip = db.query(Clip).filter(Clip.id == clip_id, Clip.user_id == user.id).first()
    if not clip:
        raise HTTPException(status_code=404, detail="Corte não encontrado para este perfil.")

    has_tiktok_post = (
        db.query(TikTokPost.id)
        .filter(TikTokPost.user_id == user.id, TikTokPost.clip_id == clip.id)
        .first()
        is not None
    )
    blocked = _deletion_block_reason(clip, has_tiktok_post=has_tiktok_post)
    if blocked:
        raise HTTPException(status_code=409, detail=blocked)

    paths = _file_paths(clip)
    db.delete(clip)
    db.commit()
    _cleanup_files(paths)
    return None


@router.post("/delete-batch", response_model=BatchDeleteResponse)
def delete_unpublished_clips_batch(
    payload: BatchDeleteRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    unique_ids = list(dict.fromkeys(payload.clip_ids))
    clips = (
        db.query(Clip)
        .filter(Clip.user_id == user.id, Clip.id.in_(unique_ids))
        .all()
    )
    by_id = {clip.id: clip for clip in clips}

    found_ids = list(by_id)
    tiktok_clip_ids = {
        row[0]
        for row in (
            db.query(TikTokPost.clip_id)
            .filter(TikTokPost.user_id == user.id, TikTokPost.clip_id.in_(found_ids))
            .all()
            if found_ids
            else []
        )
    }

    deleted_ids: list[int] = []
    cleanup_paths: list[Path] = []
    for clip_id in unique_ids:
        clip = by_id.get(clip_id)
        if not clip:
            continue
        blocked = _deletion_block_reason(clip, has_tiktok_post=clip.id in tiktok_clip_ids)
        if blocked:
            continue
        cleanup_paths.extend(_file_paths(clip))
        deleted_ids.append(clip.id)
        db.delete(clip)

    if deleted_ids:
        db.commit()
        _cleanup_files(cleanup_paths)

    return {
        "deleted": len(deleted_ids),
        "skipped": len(unique_ids) - len(deleted_ids),
        "clip_ids": deleted_ids,
    }
