from app.services.youtube_oauth import SCOPES


def test_youtube_analytics_readonly_scope_is_requested():
    assert "https://www.googleapis.com/auth/yt-analytics.readonly" in SCOPES
