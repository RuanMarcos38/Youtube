from fastapi.testclient import TestClient
from app.main import app
from app.routers import system


def test_health():
    with TestClient(app) as client:
        response = client.get('/api/health')
        assert response.status_code == 200
        body = response.json()
        assert body['status'] in {'ok', 'degraded'}
        assert 'checks' in body
        assert 'oauth_redirect_uri' in body
        assert 'youtube_download_ready' in body['checks']
        assert body['youtube_download_mode'] in {
            'guest+pot',
            'cookies+fallbacks',
            'proxy+fallbacks',
            'cookies+proxy',
        }
        assert 'ytdlp_js_runtimes' in body
        assert 'youtube_download_external_blocked' in body['checks']
        assert 'youtube_download_runtime_blocking' in body['checks']


def _healthy_runtime(monkeypatch):
    monkeypatch.setattr(system, "_worker_alive", lambda: True)
    monkeypatch.setattr(system, "_ejs_available", lambda: True)
    monkeypatch.setattr(system, "js_runtime_status", lambda: {"node": True, "deno": True})
    monkeypatch.setattr(system, "oauth_configured", lambda: True)
    monkeypatch.setattr(system, "download_auth_configured", lambda: True)
    monkeypatch.setattr(system, "download_proxy_configured", lambda: False)
    monkeypatch.setattr(system, "download_access_configured", lambda: True)
    monkeypatch.setattr(system, "_connected_profiles", lambda: 1)
    monkeypatch.setattr(system.settings, "openai_api_key", "test-openai")
    monkeypatch.setattr(system.settings, "youtube_api_key", "test-youtube")
    monkeypatch.setattr(system.settings, "ytdlp_pot_provider_url", "")
    monkeypatch.setattr(system.shutil, "which", lambda _name: "/usr/bin/tool")


def test_youtube_ip_challenge_does_not_degrade_internal_health(monkeypatch):
    _healthy_runtime(monkeypatch)
    monkeypatch.setattr(
        system,
        "read_download_probe",
        lambda: {
            "ok": False,
            "failure_kind": "youtube_ip_challenge",
            "bot_blocked": True,
            "error": "Sign in to confirm you're not a bot",
        },
    )

    body = system.health()

    assert body["status"] == "ok"
    assert body["checks"]["youtube_download_probe_ok"] is False
    assert body["checks"]["youtube_download_external_blocked"] is True
    assert body["checks"]["youtube_download_runtime_blocking"] is False


def test_network_probe_failure_degrades_internal_health(monkeypatch):
    _healthy_runtime(monkeypatch)
    monkeypatch.setattr(
        system,
        "read_download_probe",
        lambda: {
            "ok": False,
            "failure_kind": "network_unreachable",
            "bot_blocked": False,
            "error": "No route to host",
        },
    )

    body = system.health()

    assert body["status"] == "degraded"
    assert body["checks"]["youtube_download_external_blocked"] is False
    assert body["checks"]["youtube_download_runtime_blocking"] is True
