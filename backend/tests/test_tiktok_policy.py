from app.services.tiktok_policy import is_unaudited_error_text


def test_detects_tiktok_unaudited_api_code():
    assert is_unaudited_error_text("unaudited_client_can_only_post_to_private_accounts")


def test_detects_legacy_portuguese_unaudited_message():
    assert is_unaudited_error_text("TikTok: o app ainda está marcado como não auditado.")


def test_does_not_confuse_rate_limit_with_audit_restriction():
    assert not is_unaudited_error_text("rate_limit_exceeded")
