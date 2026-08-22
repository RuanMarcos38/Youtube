import hmac

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..config import settings
from ..database import get_db
from ..models import SystemSetting, User
from ..services.billing import apply_kiwify_webhook, plan_payload


router = APIRouter(prefix="/billing", tags=["billing"])


def _webhook_token(db: Session) -> str:
    row = db.get(SystemSetting, "kiwify_webhook_token")
    if row and row.value.strip():
        return row.value.strip()
    return settings.kiwify_webhook_token.strip()


@router.get("/public")
def public_billing_config():
    return {
        "checkout_url": settings.kiwify_checkout_url,
        "upgrade_url": settings.kiwify_upgrade_url,
        "base_plan_job_limit": max(1, settings.base_plan_job_limit),
    }


@router.get("/me")
def my_billing(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = plan_payload(db, user.tenant_id)
    payload.update({
        "checkout_url": settings.kiwify_checkout_url,
        "upgrade_url": settings.kiwify_upgrade_url,
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
