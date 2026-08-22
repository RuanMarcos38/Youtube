from app.services import downloader


def _clear_auth(monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_cookie_file", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_cookies_b64", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_proxy_url", "")
    monkeypatch.setattr(downloader, "cookie_override_file", lambda: None)
    monkeypatch.setattr(downloader, "effective_proxy_url", lambda: "")


def test_base_options_does_not_force_ipv4(tmp_path, monkeypatch):
    _clear_auth(monkeypatch)
    monkeypatch.setattr(downloader, "YTDLP_CACHE_DIR", tmp_path / "cache")

    options = downloader._base_options(tmp_path, include_cookies=False)

    assert "source_address" not in options
    assert options["sleep_interval_requests"] == 1


def test_pot_strategy_can_skip_webpage(monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "http://127.0.0.1:4416")

    args = downloader._pot_provider_args("mweb", skip_webpage=True)

    assert args["extractor_args"]["youtube"]["player_client"] == ["mweb"]
    assert args["extractor_args"]["youtube"]["fetch_pot"] == ["always"]
    assert args["extractor_args"]["youtube"]["player_skip"] == ["webpage", "configs"]


def test_guest_strategies_include_hls_and_ipv6(monkeypatch):
    _clear_auth(monkeypatch)
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "http://127.0.0.1:4416")
    monkeypatch.setattr(downloader.socket, "has_ipv6", True)

    strategies = downloader._strategy_variants()
    by_name = {name: variant for name, variant, _ in strategies}

    assert "guest:web_safari:hls:skip-webpage" in by_name
    assert "m3u8" in by_name["guest:web_safari:hls:skip-webpage"]["format"]
    assert by_name["guest:ipv6:mweb+pot"]["source_address"] == "::"
    assert by_name["guest:ipv6:web_safari:hls"]["source_address"] == "::"
