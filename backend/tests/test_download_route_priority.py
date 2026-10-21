from app.services import downloader, runtime_download_auth as auth


def test_existing_server_proxy_takes_priority_over_enabled_desktop(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "residential_enabled", lambda _: True)
    monkeypatch.setattr(auth, "proxy_override_url", lambda: "http://proxy.example:8080")
    assert auth.effective_proxy_url() == "http://proxy.example:8080"


def test_relay_remains_required_without_server_proxy(monkeypatch, tmp_path):
    monkeypatch.setattr(auth, "residential_enabled", lambda _: True)
    monkeypatch.setattr(auth, "proxy_override_url", lambda: "")
    monkeypatch.setattr(auth.settings, "ytdlp_proxy_url", "")
    assert auth.effective_proxy_url() == f"http://127.0.0.1:{auth.PROXY_PORT}"
    monkeypatch.setattr(downloader, "residential_status", lambda _: {"enabled": True, "connected": False})
    result = downloader.validate_download_session()
    assert result["ok"] is False
    assert result["attempts"] == 0


def test_offline_relay_does_not_prevent_configured_route_probe(monkeypatch):
    monkeypatch.setattr(downloader, "residential_status", lambda _: {"enabled": True, "connected": False})
    monkeypatch.setattr(downloader, "permanent_proxy_url", lambda: "http://proxy.example:8080")
    # An empty strategy list proves the offline early return was bypassed,
    # without making any third-party network request.
    monkeypatch.setattr(downloader, "_strategy_variants", lambda: [])
    result = downloader.validate_download_session()
    assert result["mode"] != "residential"

