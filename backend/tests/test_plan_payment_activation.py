import uuid

import pytest
from fastapi import HTTPException

from app.database import SessionLocal
from app.models import SystemSetting, Tenant, TenantPlan, User, YouTubeConnection
from app.routers.youtube_auth import _ensure_channel_connection_allowed
from app.services.asaas import PENDING_CHECKOUT_PREFIX, apply_asaas_webhook, create_checkout
from app.services.database_bootstrap import initialize_database
from app.services.plans import PLAN_CATALOG


EXPECTED_LIMITS = {
    "creator": (180, 30, 1, 1),
    "pro": (600, 120, 3, 3),
    "business": (1500, 350, 7, 10),
    "agency": (4000, 1000, 20, 25),
}


def _account(db, *, plan_code="trial", billing_status="trial"):
    suffix = uuid.uuid4().hex[:12]
    tenant = Tenant(name=f"Plan Test {suffix}", billing_status=billing_status)
    db.add(tenant)
    db.flush()
    user = User(
        tenant_id=tenant.id,
        email=f"plan-{suffix}@example.com",
        password_hash="test-only",
        display_name="Plan Test",
        role="owner",
        active=True,
    )
    db.add(user)
    db.flush()
    plan = TenantPlan(
        tenant_id=tenant.id,
        plan_code=plan_code,
        billing_status=billing_status,
        billing_provider="shortsflow" if plan_code == "trial" else "asaas",
        billing_cycle="monthly",
        monthly_job_limit=999999,
        unlimited=False,
    )
    db.add(plan)
    db.commit()
    return tenant, user, plan


def test_catalog_limits_match_pricing_screen():
    for code, expected in EXPECTED_LIMITS.items():
        definition = PLAN_CATALOG[code]
        actual = (
            definition["processing_minutes_limit"],
            definition["shorts_limit"],
            definition["channel_limit"],
            definition["user_limit"],
        )
        assert actual == expected


def test_checkout_paid_activates_exact_selected_plan_without_external_reference(monkeypatch):
    initialize_database()
    db = SessionLocal()
    try:
        tenant, user, plan = _account(db)
        checkout_id = f"chk_{uuid.uuid4().hex[:16]}"
        monkeypatch.setattr(
            "app.services.asaas._request",
            lambda method, path, payload=None: {
                "id": checkout_id,
                "link": f"https://asaas.test/{checkout_id}",
            },
        )

        checkout = create_checkout(db, user, "business", "monthly")
        db.refresh(plan)
        assert checkout["checkout_id"] == checkout_id
        assert plan.plan_code == "trial"
        assert plan.billing_status == "trial"
        assert plan.asaas_checkout_id == checkout_id
        assert db.get(SystemSetting, f"{PENDING_CHECKOUT_PREFIX}{checkout_id}") is not None

        result = apply_asaas_webhook(
            db,
            {
                "id": f"evt_{uuid.uuid4().hex[:16]}",
                "event": "CHECKOUT_PAID",
                "checkout": {
                    "id": checkout_id,
                    "customer": f"cus_{uuid.uuid4().hex[:10]}",
                    "billingType": "CREDIT_CARD",
                    "items": [
                        {
                            "name": "ShortsFlow Business",
                            "quantity": 1,
                            "value": 299.90,
                        }
                    ],
                },
            },
        )

        db.refresh(plan)
        db.refresh(tenant)
        assert result["plan_code"] == "business"
        assert plan.plan_code == "business"
        assert plan.billing_provider == "asaas"
        assert plan.billing_cycle == "monthly"
        assert plan.billing_status == "active"
        assert plan.subscription_value_cents == 29990
        assert tenant.billing_status == "active"
        assert db.get(SystemSetting, f"{PENDING_CHECKOUT_PREFIX}{checkout_id}") is None
    finally:
        db.close()


def test_checkout_paid_rejects_amount_different_from_selected_plan(monkeypatch):
    initialize_database()
    db = SessionLocal()
    try:
        _, user, plan = _account(db)
        checkout_id = f"chk_{uuid.uuid4().hex[:16]}"
        monkeypatch.setattr(
            "app.services.asaas._request",
            lambda method, path, payload=None: {"id": checkout_id, "link": f"https://asaas.test/{checkout_id}"},
        )
        create_checkout(db, user, "creator", "monthly")

        with pytest.raises(ValueError, match="valor confirmado"):
            apply_asaas_webhook(
                db,
                {
                    "id": f"evt_{uuid.uuid4().hex[:16]}",
                    "event": "CHECKOUT_PAID",
                    "checkout": {
                        "id": checkout_id,
                        "items": [{"quantity": 1, "value": 1.00}],
                    },
                },
            )
        db.rollback()
        db.refresh(plan)
        assert plan.plan_code == "trial"
        assert plan.billing_status == "trial"
    finally:
        db.close()


def test_channel_limit_blocks_only_new_channel_slot():
    initialize_database()
    db = SessionLocal()
    try:
        tenant, owner, plan = _account(db, plan_code="creator", billing_status="active")
        plan.billing_provider = "asaas"
        db.add(YouTubeConnection(user_id=owner.id, token_json='{"token":"existing"}', channel_id="channel-1"))
        second = User(
            tenant_id=tenant.id,
            email=f"second-{uuid.uuid4().hex[:12]}@example.com",
            password_hash="test-only",
            display_name="Second",
            role="member",
            active=True,
        )
        db.add(second)
        db.commit()

        # O perfil que já ocupa a única vaga pode trocar a Conta Google.
        _ensure_channel_connection_allowed(owner, db)

        # Um segundo perfil não pode criar uma segunda conexão no Creator.
        with pytest.raises(HTTPException) as exc:
            _ensure_channel_connection_allowed(second, db)
        assert exc.value.status_code == 402
        assert "1 canal" in str(exc.value.detail)
    finally:
        db.close()
