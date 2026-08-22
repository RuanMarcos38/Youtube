from app.services.editor_ai import _build_timeline, _invert_ranges, _merge_ranges, _split_for_rhythm


def test_merge_and_invert_ranges_keep_message_safe():
    merged = _merge_ranges([(1.0, 2.0), (1.9, 2.8), (8.0, 8.4)], duration=10.0)
    assert merged == [(1.0, 2.8), (8.0, 8.4)]

    keep = _invert_ranges(merged, duration=10.0)
    assert keep == [(0.0, 1.0), (2.8, 8.0), (8.4, 10.0)]


def test_split_for_rhythm_prefers_transcript_boundaries():
    transcript = [
        {"start": 0.0, "end": 2.9, "text": "gancho"},
        {"start": 2.9, "end": 6.1, "text": "beneficio"},
        {"start": 6.1, "end": 9.0, "text": "prova"},
    ]
    result = _split_for_rhythm([(0.0, 9.0)], transcript, max_shot=3.2)

    assert len(result) >= 2
    assert result[0][0] == 0.0
    assert result[-1][1] == 9.0
    assert all(end > start for start, end in result)


def test_timeline_keeps_separate_editable_tracks():
    timeline = _build_timeline(
        [(0.0, 2.5), (3.0, 6.0)],
        [{"start": 0.0, "end": 1.0, "text": "Oferta", "highlighted_words": ["oferta"]}],
        "tiktok_shop_sales",
        "source.mp4",
    )

    assert timeline["canvas"] == {"width": 1080, "height": 1920, "fps": 30, "aspect_ratio": "9:16"}
    assert timeline["duration"] == 5.5
    assert [track["type"] for track in timeline["tracks"]] == ["video", "audio", "captions", "effects"]
    assert len(timeline["tracks"][0]["items"]) == 2
    assert timeline["tracks"][0]["items"][0]["enabled"] is True
