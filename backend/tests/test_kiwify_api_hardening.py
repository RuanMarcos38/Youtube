from app.services.kiwify_api import _delivery_token, _webhook_identity


def test_delivery_token_is_short_stable_and_does_not_expose_secret():
    secret = "X5GAdjY9zBm6mxX70PaO8IlcFG8QHpAOJdbpd1F2KyA"
    token1 = _delivery_token(secret)
    token2 = _delivery_token(secret)
    assert token1 == token2
    assert len(token1) == 16
    assert secret not in token1
    assert token1.isalnum()


def test_webhook_identity_ignores_query_token_changes():
    first = "https://shorts.r2rmarketingdigital.com.br/api/billing/kiwify-webhook?token=abc"
    second = "https://shorts.r2rmarketingdigital.com.br/api/billing/kiwify-webhook?token=xyz"
    assert _webhook_identity(first) == _webhook_identity(second)
