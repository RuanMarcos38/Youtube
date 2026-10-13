from yt_dlp import YoutubeDL
from yt_dlp.networking.impersonate import ImpersonateTarget

from app.services import downloader


def test_chrome_fallbacks_initialize_real_ytdlp(monkeypatch):
    monkeypatch.setattr(downloader, "cookie_override_file", lambda: None)
    monkeypatch.setattr(downloader, "_environment_auth_configured", lambda: False)
    monkeypatch.delenv("CHROME_BIN", raising=False)
    strategies = [
        (name, variant)
        for name, variant, _, _ in downloader._strategy_variants()
        if name.startswith("guest:chrome")
    ]
    assert len(strategies) == 2
    for name, variant in strategies:
        assert isinstance(variant["impersonate"], ImpersonateTarget), name
        assert variant["impersonate"].client == "chrome"
        # Construction validates the target against curl-cffi. This catches the
        # previous string value without contacting YouTube or requiring cookies.
        with YoutubeDL({"quiet": True, **variant}) as ydl:
            assert ydl.params["impersonate"].client == "chrome"
