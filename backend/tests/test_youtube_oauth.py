from types import SimpleNamespace

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


def test_authorization_forces_google_account_chooser(monkeypatch):
    captured = {}

    class FakeFlow:
        code_verifier = "pkce-verifier"

        def authorization_url(self, **kwargs):
            captured.update(kwargs)
            return "https://accounts.google.com/o/oauth2/auth?test=1", "oauth-state"

    connection = SimpleNamespace(oauth_state=None, code_verifier=None)
    db = SimpleNamespace(commit=lambda: None)
    user = SimpleNamespace(id=123)

    monkeypatch.setattr(youtube_oauth, "_new_flow", lambda: FakeFlow())
    monkeypatch.setattr(youtube_oauth, "_connection", lambda _db, _user_id: connection)

    url = youtube_oauth.build_authorization_url(db, user)

    assert url.startswith("https://accounts.google.com/")
    assert captured["access_type"] == "offline"
    assert captured["include_granted_scopes"] == "true"
    assert captured["prompt"] == "select_account consent"
    assert connection.oauth_state == "oauth-state"
    assert connection.code_verifier == "pkce-verifier"
