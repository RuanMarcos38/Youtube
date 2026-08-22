from app.services import downloader


def test_pot_provider_args_are_enabled_from_settings(monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "http://shortsia-pot:4416")

    args = downloader._pot_provider_args("mweb")

    assert args == {
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb"],
                "fetch_pot": ["always"],
            },
            "youtubepot-bgutilhttp": {
                "base_url": ["http://shortsia-pot:4416"],
            },
        }
    }


def test_pot_provider_uses_one_client_per_strategy(monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "http://127.0.0.1:4416")

    args = downloader._pot_provider_args("web_safari")

    assert args["extractor_args"]["youtube"]["player_client"] == ["web_safari"]
    assert args["extractor_args"]["youtube"]["fetch_pot"] == ["always"]


def test_pot_provider_args_are_skipped_when_unset(monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "")

    assert downloader._pot_provider_args() is None


def test_compact_error_limits_repeated_ui_noise():
    message = "error " * 200

    compact = downloader._compact_error(message)

    assert len(compact) <= 500
    assert compact.endswith("...")
