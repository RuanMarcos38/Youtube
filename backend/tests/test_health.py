from fastapi.testclient import TestClient
from app.main import app


def test_health():
    with TestClient(app) as client:
        response = client.get('/api/health')
        assert response.status_code == 200
        body = response.json()
        assert body['status'] in {'ok', 'degraded'}
        assert 'checks' in body
        assert 'oauth_redirect_uri' in body
