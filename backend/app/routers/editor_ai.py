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

router = APIRouter(prefix="/editor-ai", tags=["editor-ai"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AutoEditRequest(BaseModel):
    preset: str = "tiktok_shop_sales"


class TimelineUpdateRequest(BaseModel):
    timeline: dict[str, Any] = Field(default_factory=dict)


@router.get("/presets")
def presets():
    """Return static editor presets without requiring a DB/auth round-trip.

    Presets contain no user data and are needed while the editor UI boots. Keeping
    this endpoint independent prevents a temporary session/database issue from
    breaking the entire editor with a generic HTTP 500 before upload starts.
    """
    return [
        {
            "id": key,
            "label": value["label"],
            "description": value["description"],
            "target": "TikTok Shop / Social Commerce",
        }
        for key, value in PRESETS.items()
    ]


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
    target_platform: str = Form("tiktok_shop"),
    rights_confirmed: bool = Form(False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not rights_confirmed:
        raise HTTPException(
            status_code=400,
            detail="Confirme que você possui direitos, licença ou autorização para editar e publicar este vídeo.",
        )

    allowed, reason = can_use_tool(db, user)
    if not allowed:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=reason)

    original_name = Path(file.filename or "video.mp4").name
    extension = Path(original_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Formato não suportado. Use: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
        )

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
        return queue_auto_edit(user.id, project_id, payload.preset, _now())
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
def export_tiktok_shop(project_id: str, user: User = Depends(get_current_user)):
    try:
        return queue_export(user.id, project_id, _now())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Projeto de edição não encontrado.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
