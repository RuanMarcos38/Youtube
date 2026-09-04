import json
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import Clip, TikTokPost, User
from ..schemas import (
    OAuthStartResponse,
    TikTokBatchUploadRequest,
    TikTokBatchUploadResponse,
    TikTokCreatorInfoResponse,
    TikTokOAuthStatusResponse,
)
from ..services.tiktok_oauth import (
    build_authorization_url,
    complete_oauth,
    disconnect,
    get_connection_status,
    get_creator_info,
)

router = APIRouter(prefix="/tiktok", tags=["tiktok"])


def _frontend_redirect(status_value: str, reason: str = "") -> RedirectResponse:
    query = {"tiktok": status_value}
    if reason:
        query["reason"] = reason[:120]
    return RedirectResponse(url=f"{settings.frontend_url}/?{urlencode(query)}#cortes")


@router.get("/oauth/status", response_model=TikTokOAuthStatusResponse)
def oauth_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_connection_status(db, user.id)


@router.get("/oauth/start", response_model=OAuthStartResponse)
def oauth_start(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return {"authorization_url": build_authorization_url(db, user)}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/oauth/callback")
def oauth_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if error:
        return _frontend_redirect("error", error)
    if not code or not state:
        return _frontend_redirect("error", "oauth_callback_incompleto")
    try:
        complete_oauth(db, code, state)
    except Exception:
        return _frontend_redirect("error", "oauth_nao_concluido")
    return _frontend_redirect("connected")


@router.post("/oauth/disconnect", status_code=204)
def oauth_disconnect(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    disconnect(db, user.id)


@router.post("/creator-info", response_model=TikTokCreatorInfoResponse)
def creator_info(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return get_creator_info(db, user.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _post_title(clip: Clip) -> str:
    try:
        tags = json.loads(clip.tags_json or "[]")
        if not isinstance(tags, list):
            tags = []
    except (json.JSONDecodeError, TypeError):
        tags = []
    hashtags = " ".join(f"#{str(tag).lstrip('#')}" for tag in tags[:8] if str(tag).strip())
    base = (clip.copy_text or clip.description or clip.title).strip()
    return f"{base}\n\n{hashtags}".strip()[:2200]


@router.post("/upload-batch", response_model=TikTokBatchUploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_batch(
    payload: TikTokBatchUploadRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not payload.music_usage_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirme a declaração de uso de música do TikTok antes de publicar.",
        )
    connection = get_connection_status(db, user.id)
    if not connection["connected"]:
        raise HTTPException(status_code=409, detail="Conecte o TikTok deste perfil antes de publicar.")

    try:
        creator = get_creator_info(db, user.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    options = creator.get("privacy_level_options") or []
    if payload.privacy_level not in options:
        raise HTTPException(
            status_code=400,
            detail="Selecione uma opção de privacidade permitida pelo TikTok para esta conta.",
        )

    unique_ids = list(dict.fromkeys(payload.clip_ids))
    clips = db.query(Clip).filter(Clip.user_id == user.id, Clip.id.in_(unique_ids)).all()
    by_id = {clip.id: clip for clip in clips}
    queued_ids: list[int] = []
    max_duration = int(creator.get("max_video_post_duration_sec") or 60)

    for clip_id in unique_ids:
        clip = by_id.get(clip_id)
        if not clip or not Path(clip.file_path).is_file():
            continue
        duration = max(0.0, clip.end_seconds - clip.start_seconds)
        if duration > max_duration:
            continue

        post = (
            db.query(TikTokPost)
            .filter(TikTokPost.user_id == user.id, TikTokPost.clip_id == clip.id)
            .first()
        )
        if post is None:
            post = TikTokPost(user_id=user.id, clip_id=clip.id, privacy_level=payload.privacy_level)
            db.add(post)
        elif post.status == "submitted":
            continue

        post.status = "queued"
        post.privacy_level = payload.privacy_level
        post.title = _post_title(clip)
        post.disable_comment = not payload.allow_comment or bool(creator.get("comment_disabled"))
        post.disable_duet = not payload.allow_duet or bool(creator.get("duet_disabled"))
        post.disable_stitch = not payload.allow_stitch or bool(creator.get("stitch_disabled"))
        post.publish_id = None
        post.error = None
        queued_ids.append(clip.id)

    db.commit()
    return {
        "queued": len(queued_ids),
        "skipped": len(unique_ids) - len(queued_ids),
        "clip_ids": queued_ids,
    }
