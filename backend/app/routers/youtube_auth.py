from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import User
from ..schemas import OAuthStartResponse, OAuthStatusResponse
from ..services.youtube_oauth import build_authorization_url, complete_oauth, disconnect, get_connection_status

router = APIRouter(prefix="/youtube", tags=["youtube"])


@router.get("/oauth/status", response_model=OAuthStatusResponse)
def oauth_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_connection_status(db, user.id)


@router.get("/oauth/start", response_model=OAuthStartResponse)
def oauth_start(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return {"authorization_url": build_authorization_url(db, user)}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/oauth/callback")
def oauth_callback(code: str = Query(...), state: str = Query(...), db: Session = Depends(get_db)):
    try:
        complete_oauth(db, code, state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"OAuth failed: {exc}") from exc
    return RedirectResponse(url=f"{settings.frontend_url}/?youtube=connected")


@router.post("/oauth/disconnect", status_code=204)
def oauth_disconnect(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    disconnect(db, user.id)
