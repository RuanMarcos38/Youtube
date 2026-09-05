import uuid

from app.database import SessionLocal
from app.models import SystemSetting
from app.services.database_bootstrap import initialize_database
from app.services.tiktok_policy import (
    PUBLIC_AUDIT_SETTING_PREFIX,
    clear_legacy_unaudited_state,
    is_unaudited_error_text,
    release_unaudited_public_queue,
)


def test_detects_tiktok_unaudited_api_code():
    assert is_unaudited_error_text("unaudited_client_can_only_post_to_private_accounts")


def test_detects_legacy_portuguese_unaudited_message():
    assert is_unaudited_error_text("TikTok: o app ainda está marcado como não auditado.")


def test_does_not_confuse_rate_limit_with_audit_restriction():
    assert not is_unaudited_error_text("rate_limit_exceeded")


def test_clear_legacy_unaudited_state_removes_old_public_gate():
    initialize_database()
    user_id = int(uuid.uuid4().hex[:8], 16)
    db = SessionLocal()
    try:
        key = f"{PUBLIC_AUDIT_SETTING_PREFIX}{user_id}"
        db.add(SystemSetting(key=key, value="2026-09-05T12:00:00+00:00", secret=False))
        db.commit()

        clear_legacy_unaudited_state(db, user_id=user_id)

        assert db.get(SystemSetting, key) is None
    finally:
        db.close()


def test_release_unaudited_public_queue_does_not_keep_local_public_gate():
    initialize_database()
    user_id = int(uuid.uuid4().hex[:8], 16)
    db = SessionLocal()
    try:
        key = f"{PUBLIC_AUDIT_SETTING_PREFIX}{user_id}"
        db.add(SystemSetting(key=key, value="2026-09-05T12:00:00+00:00", secret=False))
        db.commit()

        changed = release_unaudited_public_queue(db, user_id=user_id, current_post_id=0)

        assert changed == 0
        assert db.get(SystemSetting, key) is None
    finally:
        db.close()
