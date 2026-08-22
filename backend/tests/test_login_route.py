from fastapi.testclient import TestClient

from app.main import app


def test_invalid_login_returns_401_not_500():
    with TestClient(app) as client:
        response = client.post(
            "/api/auth/login",
            json={
                "email": "smoke-test-do-not-create@invalid.local",
                "password": "invalid-smoke-password",
            },
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "E-mail ou senha inválidos."
