from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..database import get_db
from ..models import Clip, Job, User
from ..schemas import ClipOut
from ..services.seo_quality import build_qualified_local_seo
from ..services.serializers import clip_to_dict


router = APIRouter(prefix="/clips", tags=["clips"])
_BLOCKED_STATUSES = {"upload_queued", "uploading", "uploaded"}


def _plain_subtitle_text(path_value: str | None) -> str:
    if not path_value:
        return ""
    path = Path(path_value)
    if not path.is_file():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""

    parts: list[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.isdigit() or "-->" in line:
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()
        if line:
            parts.append(line)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


@router.post("/{clip_id}/seo", response_model=ClipOut)
def regenerate_clip_seo(
    clip_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    clip = (
        db.query(Clip)
        .options(joinedload(Clip.job).joinedload(Job.source_video))
        .filter(Clip.id == clip_id, Clip.user_id == user.id)
        .first()
    )
    if not clip:
        raise HTTPException(status_code=404, detail="Corte não encontrado para este perfil.")
    if clip.status in _BLOCKED_STATUSES:
        raise HTTPException(
            status_code=409,
            detail="Gere ou ajuste o SEO antes de colocar o Short na fila de envio.",
        )

    source_title = clip.job.source_video.title if clip.job and clip.job.source_video else ""
    content_text = _plain_subtitle_text(clip.subtitle_path)
    if not content_text:
        content_text = " ".join(part for part in (clip.hook, clip.title, source_title) if part)

    # Regeneração manual parte novamente do conteúdo real do Short, em vez de
    # reutilizar a descrição/tags anteriores. A copy de engajamento permanece
    # intocada porque esta ação é exclusivamente de SEO de publicação.
    seo = build_qualified_local_seo(
        source_title=source_title,
        hook=clip.hook,
        content_text=content_text,
        current_title=clip.hook or clip.title,
        current_description="",
        current_tags=[],
    )

    clip.title = seo.title
    clip.description = seo.description
    clip.tags_json = json.dumps(seo.tags, ensure_ascii=False)
    db.commit()
    db.refresh(clip)
    return clip_to_dict(clip)
