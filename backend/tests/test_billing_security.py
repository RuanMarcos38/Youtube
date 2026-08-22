import uuid

from app.database import SessionLocal
from app.models import ProvisionedCredential
from app.services import billing
from app.services.database_bootstrap import initialize_database


def test_delivered_kiwify_password_is_not_retained(monkeypatch):
    initialize_database()
    suffix = uuid.uuid4().hex[:12]
    order_id = f"test-order-{suffix}"
    email = f"billing-test-{suffix}@example.com"
    monkeypatch.setattr(billing, "send_access_credentials", lambda *_args, **_kwargs: True)

    payload = {
        "order_id": order_id,
        "order_status": "paid",
        "webhook_event_type": "order_approved",
        "payment_method": "pix",
        "Customer": {"email": email, "full_name": "Billing Test"},
        "Product": {"product_id": "starter-test", "product_name": "ShortsFlow"},
    }

    db = SessionLocal()
    try:
        result = billing.apply_kiwify_webhook(db, payload)
        assert result["approved"] is True
        row = db.query(ProvisionedCredential).filter(ProvisionedCredential.order_id == order_id).one()
        assert row.delivered is True
        assert row.temporary_password == ""
    finally:
        db.close()
