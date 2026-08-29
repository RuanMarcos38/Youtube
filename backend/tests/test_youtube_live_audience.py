from app.services.youtube_live_audience import (
    LIVE_AUDIENCE_UNAVAILABLE_REASONS,
    LIVE_AUDIENCE_ZERO_REASONS,
    _sum_concurrent_viewers,
)


def test_sum_concurrent_viewers_handles_missing_and_string_values():
    items = [
        {"liveStreamingDetails": {"concurrentViewers": "12"}},
        {"liveStreamingDetails": {"concurrentViewers": 8}},
        {"liveStreamingDetails": {}},
        {},
    ]

    assert _sum_concurrent_viewers(items) == 20


def test_live_streaming_disabled_is_truthful_zero_not_unavailable():
    assert "liveStreamingNotEnabled" in LIVE_AUDIENCE_ZERO_REASONS
    assert "liveStreamingNotEnabled" not in LIVE_AUDIENCE_UNAVAILABLE_REASONS
