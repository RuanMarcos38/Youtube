from fastapi import APIRouter, Depends, HTTPException, WebSocket
from pydantic import BaseModel

from ..auth import require_superadmin
from ..config import settings
from ..models import User
from ..services.residential_proxy import PAIR_SECONDS, connection_status, relay

router = APIRouter(prefix="/admin/residential-proxy", tags=["admin"])


class PairRequest(BaseModel):
    persistent: bool = False


@router.get("")
def status(_: User = Depends(require_superadmin)):
    return connection_status(settings.data_path)


@router.post("/pair")
def pair(request: PairRequest | None = None, _: User = Depends(require_superadmin)):
    persistent = bool(request and request.persistent)
    try:
        code = relay.issue_code(persistent=persistent)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"code": code, "expires_in_seconds": None if persistent else PAIR_SECONDS, "persistent": persistent}


@router.post("/disable")
async def disable(_: User = Depends(require_superadmin)):
    await relay.disable()
    return connection_status(settings.data_path)


@router.websocket("/connect")
async def connect(websocket: WebSocket):
    authorization = websocket.headers.get("Authorization", "")
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    await relay.attach(websocket, token)
