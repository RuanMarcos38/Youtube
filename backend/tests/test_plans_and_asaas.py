import uuid

from app.auth import hash_password
from app.database import SessionLocal
from app.models import Job, SourceVideo, Tenant, TenantPlan, User
from app.services.asaas import apply_asaas_webhook, external_reference
from app.services.database_bootstrap import initialize_database
from app.services.plans import get_plan_definition, quota_payload


def _tenant_with_owner(db, suffix: str):
    tenant = Tenant(name=f"Plan Test {suffix}", billing_status="pending")
    db.add(tenant)
    db.flush()
    owner = User(
        tenant_id=tenant.id,
        email=f"plan-{suffix}@example.com",
        password_hash=hash_password("testing-password-123"),
        display_name="Plan Test",
        role="owner",
        active=True,
    )
    db.add(owner)
    db.flush()
    return tenant, owner


def test_plan_catalog_has_expected_commercial_limits():
    assert get_plan_definition("creator")["monthly_price_cents"] == 7990
    assert get_plan_definition("pro")["processing_minutes_limit"] == 600
    assert get_plan_definition("business")["shorts_limit"] == 350
    assert get_plan_definition("agency")["channel_limit"] == 20


def test_asaas_paid_checkout_activates_exact_plan_idempotently():
    initialize_database()
    suffix = uuid.uuid4().hex[:12]
    db = SessionLocal()
    try:
        tenant, owner = _tenant_with_owner(db, suffix)
        plan = TenantPlan(
            tenant_id=tenant.id,
            plan_code="trial",
            billing_status="trial",
            billing_provider="shortsflow",
            monthly_job_limit=999999,
        )
        db.add(plan)
        db.commit()

        event_id = f"evt_{suffix}"
        payload = {
            "id": event_id,
            "event": "CHECKOUT_PAID",
            "checkout": {
                "id": f"checkout_{suffix}",
                "externalReference": external_reference(tenant.id, "pro", "monthly"),
                "items": [{"value": 149.90, "quantity": 1}],
            },
        }
        first = apply_asaas_webhook(db, payload)
        second = apply_asaas_webhook(db, payload)
        db.refresh(plan)
        db.refresh(tenant)

        assert first["duplicate"] is False
        assert second["duplicate"] is True
        assert plan.plan_code == "pro"
        assert plan.billing_status == "active"
        assert plan.billing_provider == "asaas"
        assert plan.subscription_value_cents == 14990
        assert tenant.billing_status == "active"
    finally:
        db.close()


def test_quota_payload_counts_minutes_shorts_channels_and_users():
    initialize_database()
    suffix = uuid.uuid4().hex[:12]
    db = SessionLocal()
    try:
        tenant, owner = _tenant_with_owner(db, suffix)
        plan = TenantPlan(
            tenant_id=tenant.id,
            plan_code="creator",
            billing_status="active",
            billing_provider="asaas",
            monthly_job_limit=999999,
        )
        db.add(plan)
        source = SourceVideo(
            tenant_id=tenant.id,
            user_id=owner.id,
            youtube_id=f"video-{suffix}",
            title="Video",
            channel_title="Canal",
            original_url="https://www.youtube.com/watch?v=test",
            thumbnail_url="",
            duration_seconds=61 * 60,
            rights_confirmed=True,
        )
        db.add(source)
        db.flush()
        db.add(Job(tenant_id=tenant.id, user_id=owner.id, source_video_id=source.id, requested_clips=3, status="queued", progress=0))
        db.commit()

        usage = quota_payload(db, plan)
        assert usage["processing_minutes_used"] == 61
        assert usage["shorts_used"] == 3
        assert usage["users_used"] == 1
        assert usage["processing_minutes_remaining"] == 119
        assert usage["shorts_remaining"] == 27
    finally:
        db.close()
