import uuid

from app.database import SessionLocal
from app.models import Tenant, TenantPlan
from app.services.asaas import apply_asaas_webhook
from app.services.database_bootstrap import initialize_database


def test_subscription_and_payment_reconcile_by_customer_then_subscription():
    initialize_database()
    suffix = uuid.uuid4().hex[:12]
    db = SessionLocal()
    try:
        tenant = Tenant(name=f"Recurring Test {suffix}", billing_status="active")
        db.add(tenant)
        db.flush()
        plan = TenantPlan(
            tenant_id=tenant.id,
            plan_code="pro",
            billing_status="active",
            billing_provider="asaas",
            monthly_job_limit=999999,
            asaas_customer_id=f"cus_{suffix}",
        )
        db.add(plan)
        db.commit()

        subscription_id = f"sub_{suffix}"
        created = apply_asaas_webhook(
            db,
            {
                "id": f"evt_sub_{suffix}",
                "event": "SUBSCRIPTION_CREATED",
                "subscription": {
                    "id": subscription_id,
                    "customer": f"cus_{suffix}",
                    "value": 149.90,
                    "cycle": "MONTHLY",
                    "externalReference": None,
                },
            },
        )
        db.refresh(plan)
        assert created["tenant_id"] == tenant.id
        assert plan.asaas_subscription_id == subscription_id

        overdue = apply_asaas_webhook(
            db,
            {
                "id": f"evt_due_{suffix}",
                "event": "PAYMENT_OVERDUE",
                "payment": {
                    "id": f"pay_{suffix}",
                    "customer": f"cus_{suffix}",
                    "subscription": subscription_id,
                    "billingType": "CREDIT_CARD",
                    "value": 149.90,
                },
            },
        )
        db.refresh(plan)
        db.refresh(tenant)
        assert overdue["tenant_id"] == tenant.id
        assert plan.billing_status == "past_due"
        assert tenant.billing_status == "past_due"
    finally:
        db.close()
