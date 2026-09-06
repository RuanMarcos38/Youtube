from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..errors import YouTubeAuthError, YouTubeQuotaError
from ..models import User, YouTubeConnection
from ..schemas import OAuthStartResponse, OAuthStatusResponse, YouTubeLiveAudience, YouTubeLiveMetrics
from ..services.billing import ACTIVE_BILLING, ensure_plan
from ..services.plans import can_connect_channel
from ..services.youtube_live_audience import get_live_audience
from ..services.youtube_metrics import get_live_channel_metrics
from ..services.youtube_oauth import build_authorization_url, complete_oauth, disconnect, get_connection_status

router = APIRouter(prefix="/youtube", tags=["youtube"])


def _ensure_channel_connection_allowed(user: User, db: Session) -> None:
    if user.role == "superadmin":
        return

    # Trocar a Conta Google de um perfil que já ocupa uma vaga não aumenta a
    # quantidade de canais do tenant e, portanto, continua permitido.
    current = db.query(YouTubeConnection).filter(YouTubeConnection.user_id == user.id).first()
    if current and current.token_json:
        return

    plan = ensure_plan(db, user.tenant_id)
    if settings.billing_require_active and plan.billing_status not in ACTIVE_BILLING:
        raise HTTPException(
            status_code=402,
            detail="Sua assinatura ainda não está ativa. Conclua o pagamento para conectar um canal do YouTube.",
        )

    allowed, reason = can_connect_channel(db, plan)
    if not allowed:
        raise HTTPException(status_code=402, detail=reason)


@router.get("/oauth/status", response_model=OAuthStatusResponse)
def oauth_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return get_connection_status(db, user.id)


@router.get("/live-metrics", response_model=YouTubeLiveMetrics)
def live_metrics(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return get_live_channel_metrics(db, user.id)
    except YouTubeQuotaError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except YouTubeAuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/live-audience", response_model=YouTubeLiveAudience)
def live_audience(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        return get_live_audience(db, user.id)
    except YouTubeQuotaError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except YouTubeAuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/oauth/start", response_model=OAuthStartResponse)
def oauth_start(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_channel_connection_allowed(user, db)
    try:
        return {"authorization_url": build_authorization_url(db, user)}
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/oauth/authorize")
def oauth_authorize(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Open Google's account picker with a normal browser navigation.

    Account switching must not depend on a client-side fetch before redirecting.
    Keeping the browser on the same-origin /api route also preserves the current
    ShortsFlow session and avoids CORS/network failures caused by an external
    NEXT_PUBLIC_API_URL.
    """
    _ensure_channel_connection_allowed(user, db)
    try:
        return RedirectResponse(url=build_authorization_url(db, user), status_code=302)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _frontend_redirect(status_value: str, reason: str = "") -> RedirectResponse:
    query = {"youtube": status_value}
    if reason:
        query["reason"] = reason[:120]
    return RedirectResponse(url=f"{settings.frontend_url}/?{urlencode(query)}")


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
        # Provider/token internals must not be exposed to the browser. The user can
        # retry the account picker and diagnostics retain the server-side context.
        return _frontend_redirect("error", "oauth_nao_concluido")
    return _frontend_redirect("connected")


@router.post("/oauth/disconnect", status_code=204)
def oauth_disconnect(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    disconnect(db, user.id)
