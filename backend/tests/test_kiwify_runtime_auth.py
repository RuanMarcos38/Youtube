from pathlib import Path

from app.services import runtime_kiwify_auth
from app.services.kiwify_api import _webhook_identity


def test_webhook_identity_ignores_query_token():
    first = _webhook_identity("https://shorts.example.com/api/billing/kiwify-webhook?token=abc")
    second = _webhook_identity("https://shorts.example.com/api/billing/kiwify-webhook?token=xyz")
    assert first == second


def test_runtime_kiwify_credentials_persist_without_exposing_secret(tmp_path: Path, monkeypatch):
    target = tmp_path / "kiwify.json"
    monkeypatch.setattr(runtime_kiwify_auth, "CREDENTIALS_FILE", target)

    runtime_kiwify_auth.save_credentials(
        client_id="client-12345",
        client_secret="secret-12345",
        account_id="account-123",
    )
    loaded = runtime_kiwify_auth.load_credentials()
    status = runtime_kiwify_auth.status_payload()

    assert loaded["client_secret"] == "secret-12345"
    assert status["client_id"] == "client-12345"
    assert status["account_id"] == "account-123"
    assert status["client_secret_configured"] is True
    assert "client_secret" not in status


def test_account_id_rejects_email(tmp_path: Path, monkeypatch):
    target = tmp_path / "kiwify.json"
    monkeypatch.setattr(runtime_kiwify_auth, "CREDENTIALS_FILE", target)
    try:
        runtime_kiwify_auth.save_credentials(
            client_id="client-12345",
            client_secret="secret-12345",
            account_id="admin@example.com",
        )
    except ValueError as exc:
        assert "Account ID" in str(exc)
    else:
        raise AssertionError("email must not be accepted as Kiwify account_id")
