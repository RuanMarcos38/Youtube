from app.services import youtube_oauth


def test_oauth_env_client_config(monkeypatch):
    monkeypatch.setattr(youtube_oauth.settings, "google_oauth_client_id", "client-id")
    monkeypatch.setattr(youtube_oauth.settings, "google_oauth_client_secret", "client-secret")
    monkeypatch.setattr(youtube_oauth.settings, "google_oauth_project_id", "project")
    monkeypatch.setattr(youtube_oauth.settings, "youtube_oauth_redirect_uri", "https://example.com/api/youtube/oauth/callback")

    config = youtube_oauth._env_client_config()

    assert config is not None
    assert config["web"]["client_id"] == "client-id"
    assert config["web"]["client_secret"] == "client-secret"
    assert config["web"]["redirect_uris"] == ["https://example.com/api/youtube/oauth/callback"]


def test_oauth_configured_from_environment(monkeypatch):
    monkeypatch.setattr(youtube_oauth.settings, "google_oauth_client_id", "client-id")
    monkeypatch.setattr(youtube_oauth.settings, "google_oauth_client_secret", "client-secret")
    assert youtube_oauth.oauth_configured() is True
