from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import require_superadmin
from ..config import settings
from ..database import get_db
from ..models import Job, PaymentEvent, ProvisionedCredential, SystemSetting, Tenant, TenantPlan, User, YouTubeConnection
from ..services.billing import ensure_plan, jobs_used
from ..services.runtime_download_auth import (
    clear_cookie_override,
    clear_proxy_override,
    set_cookie_override,
    set_proxy_override,
    status_payload as download_auth_status,
)


router = APIRouter(prefix="/admin", tags=["admin"])


class PlanUpdate(BaseModel):
    plan_code: str | None = Field(default=None, max_length=40)
    billing_status: str | None = Field(default=None, max_length=30)
    monthly_job_limit: int | None = Field(default=None, ge=1, le=100000)
    unlimited: bool | None = None


class DownloadAuthUpdate(BaseModel):
    cookies_b64: str | None = None
    proxy_url: str | None = None
    clear_cookies: bool = False
    clear_proxy: bool = False


class CredentialDelivered(BaseModel):
    delivered: bool = True


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


@router.get("/dashboard")
def dashboard(_: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    active_plans = (
        db.query(TenantPlan)
        .filter(TenantPlan.billing_status.in_(["active", "paid", "trial"]), TenantPlan.plan_code != "admin")
        .all()
    )
    monthly_revenue = (
        db.query(func.coalesce(func.sum(PaymentEvent.amount_cents), 0))
        .filter(PaymentEvent.order_status == "paid", PaymentEvent.created_at >= _month_start())
        .scalar()
        or 0
    )
    total_revenue = (
        db.query(func.coalesce(func.sum(PaymentEvent.amount_cents), 0))
        .filter(PaymentEvent.order_status == "paid")
        .scalar()
        or 0
    )
    return {
        "total_users": db.query(User).filter(User.role != "superadmin").count(),
        "active_subscribers": len(active_plans),
        "monthly_revenue_cents": int(monthly_revenue),
        "total_revenue_cents": int(total_revenue),
        "jobs_this_month": db.query(Job).filter(Job.created_at >= _month_start()).count(),
        "unlimited_subscribers": sum(1 for plan in active_plans if plan.unlimited),
    }


@router.get("/users")
def users(_: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    rows = db.query(User).order_by(User.created_at.desc()).all()
    connection_map = {
        item.user_id: item
        for item in db.query(YouTubeConnection).filter(YouTubeConnection.user_id.in_([row.id for row in rows])).all()
    } if rows else {}
    result = []
    for user in rows:
        plan = ensure_plan(db, user.tenant_id)
        tenant = db.get(Tenant, user.tenant_id)
        connection = connection_map.get(user.id)
        result.append({
            "id": user.id,
            "tenant_id": user.tenant_id,
            "workspace": tenant.name if tenant else "",
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "active": user.active,
            "plan_code": plan.plan_code,
            "billing_status": plan.billing_status,
            "monthly_job_limit": plan.monthly_job_limit,
            "unlimited": plan.unlimited,
            "jobs_used": jobs_used(db, user.tenant_id),
            "subscription_value_cents": plan.subscription_value_cents,
            "youtube_connected": bool(connection and connection.token_json),
            "youtube_channel_title": connection.channel_title if connection else None,
            "created_at": user.created_at,
        })
    return result


@router.patch("/users/{user_id}/plan")
def update_plan(user_id: int, payload: PlanUpdate, _: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    if user.role == "superadmin":
        raise HTTPException(status_code=400, detail="O plano do superadministrador não pode ser reduzido.")
    plan = ensure_plan(db, user.tenant_id)
    if payload.plan_code is not None:
        plan.plan_code = payload.plan_code.strip() or plan.plan_code
    if payload.billing_status is not None:
        plan.billing_status = payload.billing_status.strip() or plan.billing_status
        tenant = db.get(Tenant, user.tenant_id)
        if tenant:
            tenant.billing_status = plan.billing_status
    if payload.monthly_job_limit is not None:
        plan.monthly_job_limit = payload.monthly_job_limit
    if payload.unlimited is not None:
        plan.unlimited = payload.unlimited
        if payload.unlimited:
            plan.plan_code = "unlimited"
    db.commit()
    return {"ok": True}


@router.get("/provisioned-credentials")
def provisioned_credentials(_: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    rows = (
        db.query(ProvisionedCredential)
        .filter(ProvisionedCredential.delivered.is_(False))
        .order_by(ProvisionedCredential.created_at.desc())
        .limit(100)
        .all()
    )
    result = []
    for row in rows:
        user = db.get(User, row.user_id)
        result.append({
            "id": row.id,
            "order_id": row.order_id,
            "email": user.email if user else "",
            "display_name": user.display_name if user else "",
            "temporary_password": row.temporary_password,
            "created_at": row.created_at,
        })
    return result


@router.patch("/provisioned-credentials/{credential_id}")
def mark_credential_delivered(
    credential_id: int,
    payload: CredentialDelivered,
    _: User = Depends(require_superadmin),
    db: Session = Depends(get_db),
):
    row = db.get(ProvisionedCredential, credential_id)
    if not row:
        raise HTTPException(status_code=404, detail="Credencial não encontrada.")
    row.delivered = payload.delivered
    if payload.delivered:
        row.temporary_password = ""
    db.commit()
    return {"ok": True}


@router.get("/download-auth")
def get_download_auth(_: User = Depends(require_superadmin)):
    return download_auth_status()


@router.put("/download-auth")
def update_download_auth(payload: DownloadAuthUpdate, _: User = Depends(require_superadmin)):
    try:
        if payload.clear_cookies:
            clear_cookie_override()
        if payload.clear_proxy:
            clear_proxy_override()
        if payload.cookies_b64 is not None and payload.cookies_b64.strip():
            set_cookie_override(payload.cookies_b64)
        if payload.proxy_url is not None:
            set_proxy_override(payload.proxy_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return download_auth_status()


@router.get("/kiwify")
def kiwify_settings(_: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    row = db.get(SystemSetting, "kiwify_webhook_token")
    token = row.value.strip() if row else ""
    webhook_url = f"{settings.frontend_url.rstrip('/')}/api/billing/kiwify-webhook?token={token}" if token else ""
    return {
        "webhook_url": webhook_url,
        "checkout_url": settings.kiwify_checkout_url,
        "upgrade_url": settings.kiwify_upgrade_url,
        "events": [
            "compra_aprovada/order_approved",
            "compra_reembolsada/order_refunded",
            "chargeback",
            "subscription_canceled",
            "subscription_late",
            "subscription_renewed",
        ],
    }
