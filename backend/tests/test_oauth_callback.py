from fastapi.testclient import TestClient

from app.main import app


def test_oauth_provider_error_redirects_to_frontend():
    with TestClient(app) as client:
        response = client.get(
            "/api/youtube/oauth/callback?error=access_denied&state=test-state",
            follow_redirects=False,
        )
        assert response.status_code in {302, 307}
        location = response.headers["location"]
        assert "youtube=error" in location
        assert "reason=access_denied" in location


def test_oauth_incomplete_callback_redirects_instead_of_422():
    with TestClient(app) as client:
        response = client.get("/api/youtube/oauth/callback", follow_redirects=False)
        assert response.status_code in {302, 307}
        assert "youtube=error" in response.headers["location"]
