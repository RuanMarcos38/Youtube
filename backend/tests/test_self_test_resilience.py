from datetime import datetime, timezone

from app.services import self_test


def test_download_check_without_probe_is_structured_and_nonfatal(monkeypatch):
    monkeypatch.setattr(self_test, "read_download_probe", lambda: None)

    download, check = self_test._download_check_from_probe()

    assert download["ok"] is False
    assert download["mode"] == "pending"
    assert check["name"] == "Download real do YouTube"
    assert check["ok"] is False
    assert check["required"] is False
    assert "assíncrono" in check["recommendation"]


def test_bot_blocked_cached_probe_does_not_raise(monkeypatch):
    monkeypatch.setattr(
        self_test,
        "read_download_probe",
        lambda: {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "ok": False,
            "mode": "guest",
            "strategy": None,
            "attempts": 12,
            "bot_blocked": True,
            "error": "Sign in to confirm you're not a bot",
        },
    )

    download, check = self_test._download_check_from_probe()

    assert download["bot_blocked"] is True
    assert check["ok"] is False
    assert check["required"] is False
    assert "proxy residencial/estático" in check["recommendation"]


def test_successful_recent_probe_is_reported_ok(monkeypatch):
    monkeypatch.setattr(
        self_test,
        "read_download_probe",
        lambda: {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "ok": True,
            "mode": "proxy",
            "strategy": "auth:mweb+pot",
            "attempts": 2,
            "bot_blocked": False,
            "error": "",
        },
    )

    download, check = self_test._download_check_from_probe()

    assert download["ok"] is True
    assert check["ok"] is True
    assert check["recommendation"] == ""


def test_google_oauth_check_explains_external_access_denied(monkeypatch):
    monkeypatch.setattr(self_test, "oauth_configured", lambda: True)
    monkeypatch.setattr(
        self_test.settings,
        "youtube_oauth_redirect_uri",
        "https://shorts.r2rmarketingdigital.com.br/api/youtube/oauth/callback",
    )

    ok, detail = self_test._google_oauth_check()

    assert ok is True
    assert "403 access_denied" in detail
    assert "Test users" in detail
    assert "https://shorts.r2rmarketingdigital.com.br/api/youtube/oauth/callback" in detail
