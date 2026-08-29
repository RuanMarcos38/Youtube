from app.services.youtube_live_audience import _sum_concurrent_viewers


def test_sum_concurrent_viewers_handles_missing_and_string_values():
    items = [
        {"liveStreamingDetails": {"concurrentViewers": "12"}},
        {"liveStreamingDetails": {"concurrentViewers": 8}},
        {"liveStreamingDetails": {}},
        {},
    ]

    assert _sum_concurrent_viewers(items) == 20
