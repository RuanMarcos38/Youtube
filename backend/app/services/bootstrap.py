import secrets

from ..config import settings
from ..database import SessionLocal
from ..models import SystemSetting, Tenant, TenantPlan, User


ADMIN_CREDENTIAL_VERSION = "2026-08-22-admin-v2"


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


def _apply_admin_credential_once(db, user: User, password_hash: str) -> None:
    """Reset the bootstrap admin password exactly once for this credential version.

    This guarantees that the generated administrator credential works after the
    deployment without forcing that password back on every future restart.
    """
    key = "admin_bootstrap_credential_version"
    row = db.get(SystemSetting, key)
    if row and row.value == ADMIN_CREDENTIAL_VERSION:
        return
    user.password_hash = password_hash
    if row:
        row.value = ADMIN_CREDENTIAL_VERSION
        row.secret = False
    else:
        db.add(SystemSetting(key=key, value=ADMIN_CREDENTIAL_VERSION, secret=False))


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
            _apply_admin_credential_once(db, user, password_hash)
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
        db.add(SystemSetting(
            key="admin_bootstrap_credential_version",
            value=ADMIN_CREDENTIAL_VERSION,
            secret=False,
        ))
        db.commit()
    finally:
        db.close()
