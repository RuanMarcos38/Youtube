import base64
import os

import pytest

from app.services import downloader


def test_pot_provider_args_are_enabled_from_settings(monkeypatch):
    monkeypatch.delenv("CHROME_BIN", raising=False)
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
    monkeypatch.delenv("CHROME_BIN", raising=False)
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "http://127.0.0.1:4416")

    args = downloader._pot_provider_args("web_safari")

    assert args["extractor_args"]["youtube"]["player_client"] == ["web_safari"]
    assert args["extractor_args"]["youtube"]["fetch_pot"] == ["always"]


def test_pot_strategy_still_requests_token_when_server_unset(monkeypatch):
    monkeypatch.delenv("CHROME_BIN", raising=False)
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "")

    args = downloader._pot_provider_args("mweb")

    assert args["extractor_args"]["youtube"]["fetch_pot"] == ["always"]
    assert "youtubepot-bgutilhttp" not in args["extractor_args"]


def test_pot_provider_passes_production_chromium_to_wpc(tmp_path, monkeypatch):
    chromium = tmp_path / "chromium"
    chromium.write_text("", encoding="utf-8")
    monkeypatch.setenv("CHROME_BIN", str(chromium))
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "")

    args = downloader._pot_provider_args("mweb")

    assert args["extractor_args"]["youtubepot-wpc"]["browser_path"] == [str(chromium)]


def test_base_options_enable_available_js_runtime_and_proxy(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_cookie_file", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_cookies_b64", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_proxy_url", "http://proxy.internal:8080")
    monkeypatch.setattr(downloader.settings, "ytdlp_node_path", "/usr/local/bin/node")
    monkeypatch.setattr(downloader, "YTDLP_CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(downloader, "_runtime_binary", lambda name: "/opt/venv/bin/deno" if name == "deno" else None)

    options = downloader._base_options(tmp_path)

    assert options["js_runtimes"]["node"] == {"path": "/usr/local/bin/node"}
    assert options["js_runtimes"]["deno"] == {"path": "/opt/venv/bin/deno"}
    assert options["proxy"] == "http://proxy.internal:8080"
    assert options["source_address"] == "0.0.0.0"
    assert options["concurrent_fragment_downloads"] >= 1


def test_base_options_register_safe_progress_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_cookie_file", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_cookies_b64", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_proxy_url", "")
    monkeypatch.setattr(downloader, "YTDLP_CACHE_DIR", tmp_path / "cache")
    events = []

    options = downloader._base_options(tmp_path, progress_hook=events.append)
    options["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 10})

    assert events == [{"status": "downloading", "downloaded_bytes": 10}]


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
    if os.name != "nt":
        assert runtime_cookie.stat().st_mode & 0o777 == 0o600


def test_runtime_cookie_file_is_unique_per_job(tmp_path, monkeypatch):
    runtime_cookie = tmp_path / "youtube-cookies.txt"
    monkeypatch.setattr(downloader, "COOKIE_RUNTIME_FILE", runtime_cookie)

    first = downloader._runtime_cookie_file(tmp_path / "jobs" / "13")
    second = downloader._runtime_cookie_file(tmp_path / "jobs" / "14")

    assert first != second
    assert first.parent == runtime_cookie.parent
    assert second.parent == runtime_cookie.parent


def test_invalid_base64_cookie_is_rejected(monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_cookie_file", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_cookies_b64", "not-valid-base64$$$")

    with pytest.raises(downloader.DownloadError, match="Base64"):
        downloader._resolve_cookie_file()


def test_guest_strategies_include_pot_hls_and_impersonation(monkeypatch):
    monkeypatch.setattr(downloader.settings, "ytdlp_cookie_file", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_cookies_b64", "")
    monkeypatch.setattr(downloader.settings, "ytdlp_pot_provider_url", "http://127.0.0.1:4416")

    names = [name for name, _, _ in downloader._strategy_variants()]

    assert "guest:mweb+pot" in names
    assert "guest:web_safari" in names
    assert "guest:tv" in names
    assert "guest:chrome+mweb+pot" in names
    assert not any("ipv6" in name for name in names)


def test_bot_challenge_without_proxy_has_actionable_message(tmp_path, monkeypatch):
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

    with pytest.raises(downloader.DownloadError, match="proxy residencial/estático"):
        downloader.download_video("https://www.youtube.com/watch?v=test", tmp_path / "job")


def test_primary_failure_prefers_youtube_challenge_over_network_noise():
    errors = [
        "Sign in to confirm you're not a bot",
        "HTTPSConnection(host='www.youtube.com'): Network is unreachable",
    ]

    assert downloader._primary_failure(errors) == "Sign in to confirm you're not a bot"


def test_compact_error_limits_repeated_ui_noise():
    message = "error " * 200

    compact = downloader._compact_error(message)

    assert len(compact) <= 500
    assert compact.endswith("...")
