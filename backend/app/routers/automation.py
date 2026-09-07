from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..services.automatic_mode_guard import automation_status, load_auto_config, run_user_automatic_mode, save_auto_config

router = APIRouter(prefix="/automation", tags=["automation"])


class AutomaticModeUpdate(BaseModel):
    enabled: bool | None = None
    keyword: str | None = Field(default=None, max_length=120)
    region: str | None = Field(default=None, min_length=2, max_length=2)
    days: int | None = Field(default=None, ge=1, le=90)
    min_views: int | None = Field(default=None, ge=0)
    min_likes: int | None = Field(default=None, ge=0)
    daily_target: int | None = Field(default=None, ge=1, le=15)
    publish_youtube: bool | None = None
    publish_tiktok: bool | None = None
    publish_start_hour: int | None = Field(default=None, ge=0, le=23)
    publish_end_hour: int | None = Field(default=None, ge=1, le=24)
    timezone: str | None = Field(default=None, max_length=64)
    rights_confirmed: bool | None = None
    music_usage_confirmed: bool | None = None
    tiktok_privacy_level: str | None = Field(default=None, max_length=50)
    allow_comment: bool | None = None
    allow_duet: bool | None = None
    allow_stitch: bool | None = None
    max_active_jobs: int | None = Field(default=None, ge=1, le=2)
    # Regra protegida do Modo Automático. O cliente pode enviar `true` para
    # refletir a UI, mas nunca pode desativar a limpeza obrigatória.
    remove_generated_captions: bool | None = None


def _payload_dict(payload: AutomaticModeUpdate) -> dict[str, Any]:
    data = payload.model_dump(exclude_none=True)
    caption_rule = data.pop("remove_generated_captions", None)
    if caption_rule is False:
        raise ValueError(
            "A remoção da legenda gerada pelo ShortsFlow é obrigatória no Modo Automático e não pode ser desativada."
        )
    return data


def _protected_config(config: dict) -> dict:
    # A regra é exposta explicitamente para a interface/API, mas não depende de
    # configuração persistida. Assim ela permanece sempre ativa, inclusive para
    # usuários/configurações criados antes desta proteção.
    protected = dict(config)
    protected["remove_generated_captions"] = True
    return protected


def _protected_status(status: dict) -> dict:
    protected = dict(status)
    protected["caption_removal_required"] = True
    return protected


@router.get("")
def get_automatic_mode(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    config = load_auto_config(db, user.id)
    return {
        "config": _protected_config(config),
        "status": _protected_status(automation_status(db, user.id, config)),
    }


@router.put("")
def update_automatic_mode(
    payload: AutomaticModeUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        config = save_auto_config(db, user.id, _payload_dict(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "config": _protected_config(config),
        "status": _protected_status(automation_status(db, user.id, config)),
    }


@router.post("/run-now")
def run_automatic_mode_now(user: User = Depends(get_current_user)):
    result = run_user_automatic_mode(user.id)
    if result.get("reason") == "rights_not_confirmed":
        raise HTTPException(status_code=409, detail="Confirme os direitos/licença/autorização antes de executar o modo automático.")
    return result
