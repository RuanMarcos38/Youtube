from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from ..config import settings
from ..schemas import OAuthStartResponse, OAuthStatusResponse
from ..services.youtube_oauth import build_authorization_url, complete_oauth, disconnect, get_connection_status

router = APIRouter(prefix="/youtube", tags=["youtube"])


@router.get("/oauth/status", response_model=OAuthStatusResponse)
def oauth_status():
    return get_connection_status()


@router.get("/oauth/start", response_model=OAuthStartResponse)
def oauth_start():
    try:
        return {"authorization_url": build_authorization_url()}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/oauth/callback")
def oauth_callback(code: str = Query(...), state: str = Query(...)):
    try:
        complete_oauth(code, state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"OAuth failed: {exc}") from exc
    return RedirectResponse(url=f"{settings.frontend_url}/?youtube=connected")


@router.post("/oauth/disconnect", status_code=204)
def oauth_disconnect():
    disconnect()
