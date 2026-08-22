import json
import secrets
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..auth import hash_password, normalize_email
from ..config import settings
from ..models import Job, PaymentEvent, ProvisionedCredential, SystemSetting, Tenant, TenantPlan, User
from .email_service import send_access_credentials
from .system_config import get_base_plan_job_limit


ACTIVE_BILLING = {"active", "paid", "trial"}


def ensure_plan(db: Session, tenant_id: int) -> TenantPlan:
    plan = db.query(TenantPlan).filter(TenantPlan.tenant_id == tenant_id).first()
    if plan:
        return plan
    tenant = db.get(Tenant, tenant_id)
    status = tenant.billing_status if tenant else "pending"
    plan = TenantPlan(
        tenant_id=tenant_id,
        plan_code="starter",
        billing_status=status,
        monthly_job_limit=get_base_plan_job_limit(db),
        unlimited=False,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def current_month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


def jobs_used(db: Session, tenant_id: int) -> int:
    return (
        db.query(Job)
        .filter(Job.tenant_id == tenant_id, Job.created_at >= current_month_start())
        .count()
    )


def plan_payload(db: Session, tenant_id: int) -> dict:
    plan = ensure_plan(db, tenant_id)
    used = jobs_used(db, tenant_id)
    remaining = None if plan.unlimited else max(0, plan.monthly_job_limit - used)
    return {
        "plan_code": plan.plan_code,
        "billing_status": plan.billing_status,
        "monthly_job_limit": plan.monthly_job_limit,
        "unlimited": plan.unlimited,
        "jobs_used": used,
        "jobs_remaining": remaining,
        "subscription_value_cents": plan.subscription_value_cents,
    }


def can_use_tool(db: Session, user: User) -> tuple[bool, str]:
    if user.role == "superadmin":
        return True, ""
    plan = ensure_plan(db, user.tenant_id)
    if settings.billing_require_active and plan.billing_status not in ACTIVE_BILLING:
        return False, "Sua assinatura ainda não está ativa. Conclua o pagamento para liberar o ShortsFlow."
    if plan.unlimited:
        return True, ""
    used = jobs_used(db, user.tenant_id)
    if used >= plan.monthly_job_limit:
        return False, "Seu limite mensal foi atingido. Faça o Upgrade para continuar usando sem limite."
    return True, ""


def _customer(payload: dict) -> dict:
    value = payload.get("Customer") or payload.get("customer") or {}
    return value if isinstance(value, dict) else {}


def _product(payload: dict) -> dict:
    value = payload.get("Product") or payload.get("product") or {}
    return value if isinstance(value, dict) else {}


def _amount_cents(payload: dict) -> int:
    commissions = payload.get("Commissions") or payload.get("commissions") or {}
    if isinstance(commissions, dict):
        value = commissions.get("charge_amount")
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            pass
    payment = payload.get("payment") or {}
    if isinstance(payment, dict):
        try:
            return int(payment.get("charge_amount") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _event_type(payload: dict) -> str:
    return str(payload.get("webhook_event_type") or payload.get("event_type") or payload.get("event") or "unknown").strip().lower()


def _setting_value(db: Session, key: str) -> str:
    row = db.get(SystemSetting, key)
    return row.value.strip() if row and row.value else ""


def _is_upgrade(db: Session, payload: dict) -> bool:
    product = _product(payload)
    product_id = str(product.get("product_id") or product.get("id") or "").strip()
    mapped_upgrade_id = _setting_value(db, "kiwify_upgrade_product_id")
    mapped_base_id = _setting_value(db, "kiwify_base_product_id")
    if product_id and mapped_upgrade_id and product_id == mapped_upgrade_id:
        return True
    if product_id and mapped_base_id and product_id == mapped_base_id:
        return False

    checkout = str(payload.get("checkout_link") or "").strip()
    if settings.kiwify_upgrade_checkout_code and settings.kiwify_upgrade_checkout_code in checkout:
        return True
    name = str(product.get("product_name") or product.get("name") or "").lower()
    return "upgrade" in name or "ilimit" in name


def _provision_user(db: Session, email: str, name: str, order_id: str) -> tuple[User, str | None]:
    user = db.query(User).filter(User.email == email).first()
    if user:
        user.active = True
        db.commit()
        return user, None

    tenant = Tenant(name=name or email.split("@", 1)[0], billing_status="active")
    db.add(tenant)
    db.flush()

    temporary_password = "SF-" + secrets.token_urlsafe(12)
    user = User(
        tenant_id=tenant.id,
        email=email,
        password_hash=hash_password(temporary_password),
        display_name=name or email.split("@", 1)[0],
        role="owner",
        active=True,
    )
    db.add(user)
    db.flush()
    credential = ProvisionedCredential(
        tenant_id=tenant.id,
        user_id=user.id,
        order_id=order_id,
        temporary_password=temporary_password,
        delivered=False,
    )
    db.add(credential)
    db.commit()
    return user, temporary_password


def apply_kiwify_webhook(db: Session, payload: dict) -> dict:
    order_id = str(payload.get("order_id") or "").strip()
    if not order_id:
        raise ValueError("Webhook da Kiwify sem order_id.")

    event_type = _event_type(payload)
    existing = (
        db.query(PaymentEvent)
        .filter(PaymentEvent.order_id == order_id, PaymentEvent.event_type == event_type)
        .first()
    )
    if existing:
        return {"ok": True, "duplicate": True, "order_id": order_id}

    customer = _customer(payload)
    product = _product(payload)
    email = normalize_email(str(customer.get("email") or payload.get("customer_email") or ""))
    name = str(customer.get("full_name") or customer.get("name") or payload.get("customer_name") or "").strip()
    order_status = str(payload.get("order_status") or payload.get("status") or "").strip().lower()
    payment_method = str(payload.get("payment_method") or "").strip().lower()
    product_id = str(product.get("product_id") or product.get("id") or "").strip()
    product_name = str(product.get("product_name") or product.get("name") or "").strip()
    amount_cents = _amount_cents(payload)

    user = db.query(User).filter(User.email == email).first() if email else None
    tenant_id = user.tenant_id if user else None
    temporary_password = None

    approved = order_status == "paid" or event_type in {"order_approved", "compra_aprovada", "subscription_renewed"}
    cancelled = event_type in {"order_refunded", "compra_reembolsada", "chargeback", "subscription_canceled", "subscription_late"}

    if approved and email:
        user, temporary_password = _provision_user(db, email, name, order_id)
        tenant_id = user.tenant_id
        tenant = db.get(Tenant, tenant_id)
        if tenant:
            tenant.billing_status = "active"

        plan = ensure_plan(db, tenant_id)
        upgrade = _is_upgrade(db, payload)
        plan.billing_status = "active"
        plan.kiwify_order_id = order_id
        plan.kiwify_product_id = product_id or plan.kiwify_product_id
        plan.kiwify_customer_email = email
        plan.subscription_value_cents = amount_cents or plan.subscription_value_cents
        if upgrade:
            plan.plan_code = "unlimited"
            plan.unlimited = True
        elif not plan.unlimited:
            plan.plan_code = "starter"
            plan.monthly_job_limit = get_base_plan_job_limit(db)
        db.commit()

        if temporary_password:
            delivered = send_access_credentials(email, name or user.display_name, temporary_password)
            if delivered:
                row = db.query(ProvisionedCredential).filter(ProvisionedCredential.order_id == order_id).first()
                if row:
                    row.delivered = True
                    db.commit()

    elif cancelled and user:
        plan = ensure_plan(db, user.tenant_id)
        plan.billing_status = "inactive"
        tenant = db.get(Tenant, user.tenant_id)
        if tenant:
            tenant.billing_status = "inactive"
        db.commit()

    event = PaymentEvent(
        tenant_id=tenant_id,
        order_id=order_id,
        order_ref=str(payload.get("order_ref") or "").strip() or None,
        event_type=event_type,
        order_status=order_status,
        payment_method=payment_method or None,
        customer_name=name,
        customer_email=email,
        product_id=product_id,
        product_name=product_name,
        amount_cents=amount_cents,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    db.add(event)
    db.commit()

    return {
        "ok": True,
        "duplicate": False,
        "order_id": order_id,
        "approved": approved,
        "provisioned": bool(user),
        "payment_method": payment_method,
    }
