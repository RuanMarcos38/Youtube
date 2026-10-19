import json
import uuid

from app.auth import hash_password
from app.database import SessionLocal
from app.models import SystemSetting, Tenant, TenantPlan, User
from app.routers import billing as billing_router
from app.services.database_bootstrap import initialize_database


def _pending_owner(db):
    suffix = uuid.uuid4().hex[:12]
    tenant = Tenant(name=f"Checkout Reopen {suffix}", billing_status="pending")
    db.add(tenant)
    db.flush()
    owner = User(
        tenant_id=tenant.id,
        email=f"checkout-reopen-{suffix}@example.com",
        password_hash=hash_password("testing-password-123"),
        display_name="Checkout Reopen",
        role="owner",
        active=True,
    )
    db.add(owner)
    db.flush()

    checkout_id = f"checkout_{suffix}"
    plan = TenantPlan(
        tenant_id=tenant.id,
        plan_code="trial",
        billing_status="trial",
        billing_provider="shortsflow",
        monthly_job_limit=999999,
        asaas_checkout_id=checkout_id,
    )
    db.add(plan)
    db.add(
        SystemSetting(
            key=f"billing.asaas.pending.{checkout_id}",
            value=json.dumps(
                {
                    "tenant_id": tenant.id,
                    "plan_code": "creator",
                    "billing_cycle": "monthly",
                    "amount_cents": 7990,
                }
            ),
            secret=False,
        )
    )
    db.commit()
    return owner, checkout_id


def test_same_pending_checkout_is_reopened_without_creating_a_second_one(monkeypatch):
    initialize_database()
    db = SessionLocal()
    try:
        owner, checkout_id = _pending_owner(db)
        monkeypatch.setattr(billing_router, "asaas_configured", lambda: True)

        def should_not_create_checkout(*args, **kwargs):
            raise AssertionError("a second Asaas checkout must not be created")

        monkeypatch.setattr(billing_router, "create_checkout", should_not_create_checkout)

        result = billing_router.create_asaas_checkout(
            billing_router.AsaasCheckoutRequest(plan_code="creator", billing_cycle="monthly"),
            user=owner,
            db=db,
        )

        assert result["checkout_id"] == checkout_id
        assert result["checkout_url"] == f"https://asaas.com/checkoutSession/show?id={checkout_id}"
        assert result["plan_code"] == "creator"
        assert result["billing_cycle"] == "monthly"
        assert result["amount_cents"] == 7990
    finally:
        db.close()


def test_different_plan_does_not_reuse_an_unrelated_pending_checkout():
    initialize_database()
    db = SessionLocal()
    try:
        owner, _ = _pending_owner(db)
        result = billing_router._reusable_asaas_checkout(db, owner, "pro", "monthly")
        assert result is None
    finally:
        db.close()
