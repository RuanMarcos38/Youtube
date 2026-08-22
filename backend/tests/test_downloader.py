import base64

import pytest

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


def test_base_options_enable_node_ejs_runtime_and_proxy(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_cookie_file", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_cookies_b64", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_proxy_url", "http://proxy.internal:8080")
    monkeypatch.setattr(downloader.settings, "ytdlp_node_path", "/usr/local/bin/node")
    monkeypatch.setattr(downloader, "YTDLP_CACHE_DIR", tmp_path / "cache")

    options = downloader._base_options(tmp_path)

    assert options["js_runtimes"] == {"node": {"path": "/usr/local/bin/node"}}
    assert options["proxy"] == "http://proxy.internal:8080"


def test_base64_cookie_is_materialized_outside_public_data_dir(tmp_path, monkeypatch):
    cookies = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2147483647\tPREF\tf6=400\n"
    monkeypatch.setattr(downloader.settings, "ytdlp_cookie_file", "")
    monkeypatch.setattr(
        downloader.settings,
        "ytdlp_cookies_b64",
        base64.b64encode(cookies.encode("utf-8")).decode("ascii"),
    )
    runtime_cookie = tmp_path / "youtube-cookies.txt"
    monkeypatch.setattr(downloader, "COOKIE_RUNTIME_FILE", runtime_cookie)

    resolved = downloader._resolve_cookie_file()

    assert resolved == str(runtime_cookie)
    assert runtime_cookie.read_text(encoding="utf-8").startswith("# Netscape HTTP Cookie File")
    assert runtime_cookie.stat().st_mode & 0o777 == 0o600


def test_invalid_base64_cookie_is_rejected(monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_cookie_file", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_cookies_b64", "not-valid-base64$$$")

    with pytest.raises(downloader.DownloadError, match="Base64"):
        downloader._resolve_cookie_file()


def test_bot_challenge_without_auth_has_actionable_message(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_cookie_file", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_cookies_b64", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_proxy_url", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "http://127.0.0.1:4416")
    monkeypatch.setattr(downloader, "YTDLP_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(
        downloader,
        "_download_with_options",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("Sign in to confirm you're not a bot")),
    )

    with pytest.raises(downloader.DownloadError, match="YTDLP_COOKIES_B64"):
        downloader.download_video("https://www.youtube.com/watch?v=test", tmp_path / "job")


def test_compact_error_limits_repeated_ui_noise():
    message = "error " * 200

    compact = downloader._compact_error(message)

    assert len(compact) <= 500
    assert compact.endswith("...")
