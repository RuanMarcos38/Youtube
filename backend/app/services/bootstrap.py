import secrets

from ..config import settings
from ..database import SessionLocal
from ..models import SystemSetting, Tenant, TenantPlan, User


def _ensure_kiwify_webhook_token(db) -> None:
    row = db.get(SystemSetting, "kiwify_webhook_token")
    if row and row.value.strip():
        return
    value = settings.kiwify_webhook_token.strip() or secrets.token_urlsafe(32)
    if row:
        row.value = value
        row.secret = True
    else:
        db.add(SystemSetting(key="kiwify_webhook_token", value=value, secret=True))
    db.commit()


def ensure_superadmin() -> None:
    email = settings.admin_bootstrap_email.strip().lower()
    password_hash = settings.admin_bootstrap_password_hash.strip()
    if not email or not password_hash:
        return

    db = SessionLocal()
    try:
        _ensure_kiwify_webhook_token(db)
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.role = "superadmin"
            user.active = True
            plan = db.query(TenantPlan).filter(TenantPlan.tenant_id == user.tenant_id).first()
            if not plan:
                plan = TenantPlan(
                    tenant_id=user.tenant_id,
                    plan_code="admin",
                    billing_status="active",
                    monthly_job_limit=999999,
                    unlimited=True,
                )
                db.add(plan)
            else:
                plan.plan_code = "admin"
                plan.billing_status = "active"
                plan.unlimited = True
            tenant = db.get(Tenant, user.tenant_id)
            if tenant:
                tenant.billing_status = "active"
            db.commit()
            return

        tenant = Tenant(name="ShortsFlow Administração", billing_status="active")
        db.add(tenant)
        db.flush()
        user = User(
            tenant_id=tenant.id,
            email=email,
            password_hash=password_hash,
            display_name="Administrador ShortsFlow",
            role="superadmin",
            active=True,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantPlan(
                tenant_id=tenant.id,
                plan_code="admin",
                billing_status="active",
                monthly_job_limit=999999,
                unlimited=True,
            )
        )
        db.commit()
    finally:
        db.close()
