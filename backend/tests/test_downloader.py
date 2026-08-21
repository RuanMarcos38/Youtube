from app.services import downloader


def test_pot_provider_args_are_enabled_from_settings(monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "http://shortsia-pot:4416")

    args = downloader._pot_provider_args()

    assert args == {
        "extractor_args": {
            "youtube": {"player_client": ["mweb", "web_safari", "tv"]},
            "youtubepot-bgutilhttp": {"base_url": ["http://shortsia-pot:4416"]},
        }
    }


def test_pot_provider_args_are_skipped_when_unset(monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "")

    assert downloader._pot_provider_args() is None
