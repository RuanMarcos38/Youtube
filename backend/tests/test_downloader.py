from app.services import downloader


def test_pot_provider_args_are_enabled_from_settings(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "http://shortsia-pot:4416")
    visitor_data_file = tmp_path / "visitor_data.txt"
    visitor_data_file.write_text("visitor-123", encoding="utf-8")
    monkeypatch.setattr(downloader, "VISITOR_DATA_FILE", visitor_data_file)

    args = downloader._pot_provider_args()

    assert args == {
        "extractor_args": {
            "youtube": {
                "player_client": ["mweb"],
                "player_skip": ["webpage", "configs"],
                "visitor_data": ["visitor-123"],
            },
            "youtubetab": {"skip": ["webpage"]},
            "youtubepot-bgutilhttp": {"base_url": ["http://shortsia-pot:4416"]},
        }
    }


def test_pot_provider_args_are_skipped_when_unset(monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "")

    assert downloader._pot_provider_args() is None
