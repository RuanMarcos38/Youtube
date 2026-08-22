from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..auth import get_current_user
from ..config import settings
from ..models import User

router = APIRouter(prefix="/media", tags=["media"])


@router.get("/{relative_path:path}")
def private_media(relative_path: str, user: User = Depends(get_current_user)):
    user_root = (settings.data_path / "users" / str(user.id)).resolve()
    target = (user_root / relative_path).resolve()
    try:
        target.relative_to(user_root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Acesso negado.") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Arquivo não encontrado.")
    return FileResponse(str(target))
