from fastapi import APIRouter, Depends, HTTPException, WebSocket

from ..auth import require_superadmin
from ..config import settings
from ..models import User
from ..services.residential_proxy import PAIR_SECONDS, connection_status, relay

router = APIRouter(prefix="/admin/residential-proxy", tags=["admin"])


@router.get("")
def status(_: User = Depends(require_superadmin)):
    return connection_status(settings.data_path)


@router.post("/pair")
def pair(_: User = Depends(require_superadmin)):
    try:
        code = relay.issue_code()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"code": code, "expires_in_seconds": PAIR_SECONDS}


@router.post("/disable")
async def disable(_: User = Depends(require_superadmin)):
    await relay.disable()
    return connection_status(settings.data_path)


@router.websocket("/connect")
async def connect(websocket: WebSocket):
    authorization = websocket.headers.get("Authorization", "")
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    await relay.attach(websocket, token)
