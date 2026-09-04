from app.services import tiktok_oauth


def test_production_redirect_uses_public_frontend_when_default_is_local(monkeypatch):
    monkeypatch.setattr(tiktok_oauth.settings, "frontend_url", "https://shorts.r2rmarketingdigital.com.br")
    monkeypatch.setattr(
        tiktok_oauth.settings,
        "tiktok_oauth_redirect_uri",
        "http://localhost:8000/api/tiktok/oauth/callback",
    )

    assert (
        tiktok_oauth.oauth_redirect_uri()
        == "https://shorts.r2rmarketingdigital.com.br/api/tiktok/oauth/callback"
    )


def test_explicit_tiktok_redirect_uri_is_preserved(monkeypatch):
    monkeypatch.setattr(tiktok_oauth.settings, "frontend_url", "https://shorts.r2rmarketingdigital.com.br")
    monkeypatch.setattr(
        tiktok_oauth.settings,
        "tiktok_oauth_redirect_uri",
        "https://oauth.example.com/tiktok/callback",
    )

    assert tiktok_oauth.oauth_redirect_uri() == "https://oauth.example.com/tiktok/callback"


def test_local_development_redirect_is_preserved(monkeypatch):
    monkeypatch.setattr(tiktok_oauth.settings, "frontend_url", "http://localhost:3000")
    monkeypatch.setattr(
        tiktok_oauth.settings,
        "tiktok_oauth_redirect_uri",
        "http://localhost:8000/api/tiktok/oauth/callback",
    )

    assert (
        tiktok_oauth.oauth_redirect_uri()
        == "http://localhost:8000/api/tiktok/oauth/callback"
    )
