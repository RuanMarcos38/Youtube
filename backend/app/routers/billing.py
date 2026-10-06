import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import get_current_user, require_owner, require_superadmin
from ..config import settings
from ..database import SessionLocal, get_db
from ..models import SystemSetting, TenantPlan, User
from ..services.asaas import (
    ASAAS_WEBHOOK_EVENTS,
    _pending_checkout,
    apply_asaas_webhook,
    asaas_configured,
    create_checkout,
    register_webhook,
    webhook_configured,
)
from ..services.billing import apply_kiwify_webhook, plan_payload_for_user
from ..services.plans import EXTRA_CHANNEL_PRICE_CENTS, public_plans
from ..services.system_config import get_public_config_safe


router = APIRouter(prefix="/billing", tags=["billing"])
logger = logging.getLogger(__name__)


class AsaasCheckoutRequest(BaseModel):
    plan_code: str = Field(pattern="^(creator|pro|business|agency)$")
    billing_cycle: str = Field(default="monthly", pattern="^(monthly|yearly)$")


def _webhook_token(db: Session) -> str:
    row = db.get(SystemSetting, "kiwify_webhook_token")
    if row and row.value.strip():
        return row.value.strip()
    return settings.kiwify_webhook_token.strip()


def _apply_new_checkout_route(payload: dict) -> dict:
    if asaas_configured():
        payload["checkout_url"] = "/planos"
        payload["upgrade_url"] = "/planos"
    return payload


def _asaas_environment_label() -> str:
    base = settings.asaas_base_url.lower()
    if "api-sandbox.asaas.com" in base:
        return "sandbox"
    if "api.asaas.com" in base:
        return "production"
    return "custom"


def _checkout_session_url(checkout_id: str) -> str:
    host = "https://sandbox.asaas.com" if "sandbox" in settings.asaas_base_url.lower() else "https://asaas.com"
    return f"{host}/checkoutSession/show?id={checkout_id}"


def _reusable_asaas_checkout(db: Session, user: User, plan_code: str, billing_cycle: str) -> dict | None:
    """Reopen the same pending Asaas checkout instead of creating a duplicate.

    Closing the hosted Asaas page does not cancel the checkout. While the
    existing checkout remains pending, a second click for the same plan/cycle
    must send the owner back to the original checkout URL. This keeps the
    one-checkout-at-a-time protection while removing the dead end in /planos.
    """
    tenant_plan = db.query(TenantPlan).filter(TenantPlan.tenant_id == user.tenant_id).first()
    if not tenant_plan or not tenant_plan.asaas_checkout_id:
        return None

    provider = (getattr(tenant_plan, "billing_provider", "") or "").strip().lower()
    billing_status = (tenant_plan.billing_status or "").strip().lower()
    if provider == "asaas" and billing_status in {"active", "paid", "past_due"}:
        return None
    if billing_status in {"inactive", "canceled", "cancelled"}:
        return None

    checkout_id = str(tenant_plan.asaas_checkout_id).strip()
    pending = _pending_checkout(db, checkout_id)
    if not pending or int(pending.get("tenant_id") or 0) != int(user.tenant_id):
        return None
    if pending.get("plan_code") != plan_code or pending.get("billing_cycle") != billing_cycle:
        return None

    return {
        "checkout_id": checkout_id,
        "checkout_url": _checkout_session_url(checkout_id),
        "plan_code": plan_code,
        "billing_cycle": billing_cycle,
        "amount_cents": int(pending.get("amount_cents") or 0),
    }


@router.get("/public")
def public_billing_config():
    db = SessionLocal()
    try:
        payload = get_public_config_safe(db)
        payload["asaas_enabled"] = asaas_configured()
        payload["plans_url"] = "/planos"
        return _apply_new_checkout_route(payload)
    finally:
        db.close()


@router.get("/plans")
def billing_plans():
    return {
        "plans": public_plans(),
        "asaas_enabled": asaas_configured(),
        "webhook_ready": webhook_configured(),
        "extra_channel_price_cents": EXTRA_CHANNEL_PRICE_CENTS,
    }


@router.get("/me")
def my_billing(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    payload = plan_payload_for_user(db, user)
    public_config = get_public_config_safe(db)
    payload.update({
        "checkout_url": public_config["checkout_url"],
        "upgrade_url": public_config["upgrade_url"],
        "asaas_enabled": asaas_configured(),
    })
    return _apply_new_checkout_route(payload)


@router.post("/asaas/checkout")
def create_asaas_checkout(
    payload: AsaasCheckoutRequest,
    user: User = Depends(require_owner),
    db: Session = Depends(get_db),
):
    if not asaas_configured():
        raise HTTPException(status_code=503, detail="O checkout Asaas ainda não foi habilitado no servidor.")

    reusable = _reusable_asaas_checkout(db, user, payload.plan_code, payload.billing_cycle)
    if reusable:
        return reusable

    try:
        return create_checkout(db, user, payload.plan_code, payload.billing_cycle)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        # Never log the API key or webhook token. The tenant/plan/environment
        # are enough to diagnose provider failures safely in EasyPanel.
        logger.warning(
            "Asaas checkout failed tenant=%s plan=%s cycle=%s environment=%s error=%s",
            user.tenant_id,
            payload.plan_code,
            payload.billing_cycle,
            _asaas_environment_label(),
            str(exc),
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/asaas/register-webhook")
def register_asaas_webhook(user: User = Depends(require_superadmin)):
    if not asaas_configured() or not webhook_configured():
        raise HTTPException(status_code=503, detail="Configure ASAAS_API_KEY e ASAAS_WEBHOOK_AUTH_TOKEN antes de registrar o webhook.")
    url = f"{settings.frontend_url.rstrip('/')}{settings.api_prefix}/billing/asaas-webhook"
    try:
        data = register_webhook(url, user.email)
    except RuntimeError as exc:
        logger.warning("Asaas webhook registration failed environment=%s error=%s", _asaas_environment_label(), str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "ok": True,
        "webhook_id": data.get("id"),
        "webhook_url": url,
        "events": ASAAS_WEBHOOK_EVENTS,
    }


@router.post("/asaas-webhook")
async def asaas_webhook(request: Request, db: Session = Depends(get_db)):
    expected = settings.asaas_webhook_auth_token.strip()
    supplied = request.headers.get("asaas-access-token", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Webhook Asaas ainda não foi configurado.")
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token do webhook Asaas inválido.")
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Payload JSON inválido.") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload do webhook inválido.")
    try:
        return apply_asaas_webhook(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
