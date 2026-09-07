from datetime import datetime
from zoneinfo import ZoneInfo

from app.services.automatic_mode import DEFAULT_AUTO_CONFIG, _normalize_config, expected_publications_now, trend_score


def test_automatic_mode_keeps_fixed_ten_clips_and_caps_daily_target():
    config = _normalize_config({**DEFAULT_AUTO_CONFIG, "clips_per_source": 3, "daily_target": 99})
    assert config["clips_per_source"] == 10
    assert config["daily_target"] == 15


def test_expected_publications_are_spread_inside_daily_window():
    config = _normalize_config({
        **DEFAULT_AUTO_CONFIG,
        "daily_target": 15,
        "publish_start_hour": 8,
        "publish_end_hour": 22,
        "timezone": "America/Sao_Paulo",
    })
    zone = ZoneInfo("America/Sao_Paulo")
    before = datetime(2026, 9, 7, 7, 30, tzinfo=zone)
    middle = datetime(2026, 9, 7, 15, 0, tzinfo=zone)
    after = datetime(2026, 9, 7, 22, 30, tzinfo=zone)
    assert expected_publications_now(config, before) == 0
    assert 7 <= expected_publications_now(config, middle) <= 9
    assert expected_publications_now(config, after) == 15


def test_trend_score_rewards_engagement():
    common = {"published_at": "2026-09-07T12:00:00Z"}
    low = trend_score({**common, "view_count": 1_000, "like_count": 20, "comment_count": 5})
    high = trend_score({**common, "view_count": 10_000, "like_count": 800, "comment_count": 100})
    assert high > low
