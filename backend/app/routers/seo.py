from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from ..auth import get_current_user
from ..config import settings
from ..services.seo_quality import clip_transcript_text
from ..database import get_db
from ..models import Clip, Job, User
from ..schemas import ClipOut
from ..services.seo_ai import SeoGenerationError, build_ai_qualified_seo
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
        # The original timed transcript survives removal of visible subtitles.
        path = settings.data_path / "users" / str(user.id) / "jobs" / str(clip.job_id) / "segments.json"
        try:
            segments = json.loads(path.read_text(encoding="utf-8"))
            content_text = clip_transcript_text(segments, clip.start_seconds, clip.end_seconds)
        except (OSError, ValueError, TypeError, AttributeError):
            content_text = ""
    if not content_text:
        raise HTTPException(status_code=422, detail="A transcrição deste corte não está disponível. O SEO atual foi mantido.")

    try:
        seo = build_ai_qualified_seo(
            source_title=source_title,
            hook=clip.hook,
            content_text=content_text,
            current_title=clip.title,
            current_description=clip.description,
            require_ai=True,
        )
    except SeoGenerationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Recheck publication state after the external call before writing metadata.
    db.refresh(clip)
    if clip.status in _BLOCKED_STATUSES:
        raise HTTPException(status_code=409, detail="O Short entrou na fila de envio durante a geração. O SEO atual foi mantido.")

    clip.title = seo.title
    clip.description = seo.description
    clip.tags_json = json.dumps(seo.tags, ensure_ascii=False)
    db.commit()
    db.refresh(clip)
    return clip_to_dict(clip)
