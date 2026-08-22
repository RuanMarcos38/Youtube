from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..services.billing import can_use_tool
from ..services.editor_ai import (
    ALLOWED_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    PRESETS,
    create_project_record,
    list_projects,
    project_dir,
    queue_auto_edit,
    queue_export,
    read_project,
    save_project,
    save_timeline,
)
from ..services.editor_ai_pro import DEFAULT_EDIT_OPTIONS, MAX_MUSIC_BYTES, MUSIC_EXTENSIONS

router = APIRouter(prefix="/editor-ai", tags=["editor-ai"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutoEditRequest(BaseModel):
    preset: str = "tiktok_shop_sales"
    captions_enabled: bool = True
    caption_style: str = "auto"
    music_mode: str = "auto"
    music_mood: str = "auto"
    music_volume: float = Field(default=0.18, ge=0.0, le=0.45)
    edit_intensity: str = "high"
    auto_reframe: bool = True
    hook_variants: bool = True


class TimelineUpdateRequest(BaseModel):
    timeline: dict[str, Any] = Field(default_factory=dict)


def _normalize_edit_options(payload: AutoEditRequest) -> dict[str, Any]:
    caption_style = payload.caption_style if payload.caption_style in {"auto", "impact", "ugc", "cinematic"} else "auto"
    music_mode = payload.music_mode if payload.music_mode in {"auto", "none", "custom"} else "auto"
    music_mood = payload.music_mood if payload.music_mood in {"auto", "energetic", "confident", "elegant", "natural"} else "auto"
    edit_intensity = payload.edit_intensity if payload.edit_intensity in {"balanced", "high", "maximum"} else "high"
    return {
        "captions_enabled": bool(payload.captions_enabled),
        "caption_style": caption_style,
        "music_mode": music_mode,
        "music_mood": music_mood,
        "music_volume": max(0.0, min(0.45, float(payload.music_volume))),
        "edit_intensity": edit_intensity,
        "auto_reframe": bool(payload.auto_reframe),
        "hook_variants": bool(payload.hook_variants),
    }


@router.get("/presets")
def presets():
    return [
        {
            "id": key,
            "label": value["label"],
            "description": value["description"],
            "target": "TikTok Shop / Reels / YouTube Shorts",
        }
        for key, value in PRESETS.items()
    ]


@router.get("/options")
def editor_options():
    return {
        "defaults": DEFAULT_EDIT_OPTIONS,
        "caption_styles": [
            {"id": "auto", "label": "Automática pela IA"},
            {"id": "impact", "label": "Impacto / Performance"},
            {"id": "ugc", "label": "UGC / Natural"},
            {"id": "cinematic", "label": "Cinematográfica"},
        ],
        "music_modes": [
            {"id": "auto", "label": "Trilha automática"},
            {"id": "custom", "label": "Minha música"},
            {"id": "none", "label": "Sem música"},
        ],
        "music_moods": [
            {"id": "auto", "label": "IA decide"},
            {"id": "energetic", "label": "Energética"},
            {"id": "confident", "label": "Confiante"},
            {"id": "elegant", "label": "Elegante"},
            {"id": "natural", "label": "Natural"},
        ],
        "edit_intensities": [
            {"id": "balanced", "label": "Equilibrada"},
            {"id": "high", "label": "Alta performance"},
            {"id": "maximum", "label": "Máxima retenção"},
        ],
    }


@router.get("/projects")
def projects(user: User = Depends(get_current_user)):
    return list_projects(user.id)


@router.get("/projects/{project_id}")
def project(project_id: str, user: User = Depends(get_current_user)):
    try:
        return read_project(user.id, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: UploadFile = File(...),
    preset: str = Form("tiktok_shop_sales"),
    target_platform: str = Form("all_social"),
    rights_confirmed: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not rights_confirmed:
        raise HTTPException(status_code=400, detail="Confirme que você possui direitos, licença ou autorização para editar e publicar este vídeo.")

    allowed, reason = can_use_tool(db, user)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)

    original_name = Path(file.filename or "video.mp4").name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Formato não suportado. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}.")

    chosen_preset = preset if preset in PRESETS else "tiktok_shop_sales"
    stored_filename = f"source{extension}"
    project = create_project_record(
        user_id=user.id,
        tenant_id=user.tenant_id,
        original_filename=original_name,
        stored_filename=stored_filename,
        preset=chosen_preset,
        target_platform=target_platform,
        created_at=_now(),
    )
    project["edit_options"] = dict(DEFAULT_EDIT_OPTIONS)
    root = project_dir(user.id, project["id"])
    target = root / stored_filename

    total = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(status_code=413, detail="O vídeo excede o limite de 500 MB.")
                output.write(chunk)
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise
    finally:
        await file.close()

    project["upload_bytes"] = total
    save_project(user.id, project["id"], project)
    return project


@router.post("/projects/{project_id}/music")
async def upload_music(
    project_id: str,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    try:
        project = read_project(user.id, project_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc

    original_name = Path(file.filename or "music.mp3").name
    extension = Path(original_name).suffix.lower()
    if extension not in MUSIC_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Formato de áudio não suportado. Use: {', '.join(sorted(MUSIC_EXTENSIONS))}.")

    root = project_dir(user.id, project_id)
    stored_name = f"custom-music{extension}"
    target = root / stored_name
    total = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = await file.read(512 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_MUSIC_BYTES:
                    target.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="A música excede o limite de 50 MB.")
                output.write(chunk)
    finally:
        await file.close()

    project["custom_music_filename"] = stored_name
    project["custom_music_original_name"] = original_name
    project["updated_at"] = _now()
    save_project(user.id, project_id, project)
    return project


@router.post("/projects/{project_id}/auto-edit", status_code=status.HTTP_202_ACCEPTED)
def auto_edit(
    project_id: str,
    payload: AutoEditRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    allowed, reason = can_use_tool(db, user)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)
    try:
        current = read_project(user.id, project_id)
        edit_options = _normalize_edit_options(payload)
        if edit_options["music_mode"] == "custom" and not current.get("custom_music_filename"):
            raise HTTPException(status_code=409, detail="Selecione e envie uma música antes de iniciar a edição com música própria.")
        queued = queue_auto_edit(user.id, project_id, payload.preset, _now())
        queued["edit_options"] = edit_options
        save_project(user.id, project_id, queued)
        return queued
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc


@router.put("/projects/{project_id}/timeline", status_code=status.HTTP_202_ACCEPTED)
def update_timeline(
    project_id: str,
    payload: TimelineUpdateRequest,
    user: User = Depends(get_current_user),
):
    try:
        return save_timeline(user.id, project_id, payload.timeline, _now())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/projects/{project_id}/export/tiktok-shop", status_code=status.HTTP_202_ACCEPTED)
def export_social_ready(project_id: str, user: User = Depends(get_current_user)):
    try:
        return queue_export(user.id, project_id, _now())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
