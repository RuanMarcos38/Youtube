import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import SessionLocal, get_db
from ..models import SystemSetting, User
from ..services.billing import apply_kiwify_webhook, plan_payload
from ..services.system_config import get_public_config_safe


router = APIRouter(prefix="/billing", tags=["billing"])


def _webhook_token(db: Session) -> str:
    row = db.get(SystemSetting, "kiwify_webhook_token")
    if row and row.value.strip():
        return row.value.strip()
    return settings.kiwify_webhook_token.strip()


@router.get("/public")
def public_billing_config():
    db = SessionLocal()
    try:
        return get_public_config_safe(db)
    finally:
        db.close()


@router.get("/me")
def my_billing(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = plan_payload(db, user.tenant_id)
    public_config = get_public_config_safe(db)
    payload.update({
        "checkout_url": public_config["checkout_url"],
        "upgrade_url": public_config["upgrade_url"],
    })
    return payload


@router.post("/kiwify-webhook")
async def kiwify_webhook(
    request: Request,
    token: str = Query(default=""),
    db: Session = Depends(get_db),
):
    expected = _webhook_token(db)
    supplied = token.strip() or request.headers.get("x-shortsflow-webhook-token", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Webhook Kiwify ainda não foi configurado.")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token do webhook inválido.")

    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Payload JSON inválido.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload do webhook inválido.")

    try:
        return apply_kiwify_webhook(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
