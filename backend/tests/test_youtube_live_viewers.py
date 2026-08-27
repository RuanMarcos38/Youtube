from app.services import youtube_metrics


class _Call:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _LiveBroadcasts:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        return _Call(self.payload)


class _Videos:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        return _Call(self.payload)


class _YouTube:
    def __init__(self, broadcasts, videos=None):
        self._broadcasts = _LiveBroadcasts(broadcasts)
        self._videos = _Videos(videos or {"items": []})

    def liveBroadcasts(self):
        return self._broadcasts

    def videos(self):
        return self._videos


def _live_item(video_id, title="Live"):
    return {
        "id": video_id,
        "snippet": {"title": title},
        "status": {"lifeCycleStatus": "live"},
    }


def _video_item(video_id, viewers):
    return {
        "id": video_id,
        "snippet": {"title": f"Video {video_id}"},
        "liveStreamingDetails": {"concurrentViewers": viewers},
    }


def test_live_viewers_none_active():
    youtube = _YouTube({"items": []})

    payload = youtube_metrics._fetch_live_viewers(youtube, user_id=1, channel_id="channel")

    assert payload["live_concurrent_viewers"] == 0
    assert payload["active_live_broadcasts"] == 0
    assert payload["live_viewers_detail"] == "Nenhuma transmissão ao vivo"


def test_live_viewers_sums_active_broadcasts():
    youtube = _YouTube(
        {"items": [_live_item("a", "Live A"), _live_item("b", "Live B"), _live_item("c", "Live C")]},
        {"items": [_video_item("a", "120"), _video_item("b", "75"), _video_item("c", "42")]},
    )

    payload = youtube_metrics._fetch_live_viewers(youtube, user_id=1, channel_id="channel")

    assert payload["live_concurrent_viewers"] == 237
    assert payload["active_live_broadcasts"] == 3
    assert payload["live_viewers_status"] == "ok"
    assert payload["live_viewers_detail"] == "3 transmissões ao vivo"


def test_live_viewers_marks_unavailable_when_counts_are_hidden():
    youtube = _YouTube(
        {"items": [_live_item("a")]},
        {"items": [{"id": "a", "snippet": {"title": "Video a"}, "liveStreamingDetails": {}}]},
    )

    payload = youtube_metrics._fetch_live_viewers(youtube, user_id=1, channel_id="channel")

    assert payload["live_concurrent_viewers"] is None
    assert payload["active_live_broadcasts"] == 1
    assert payload["live_viewers_status"] == "unavailable"
    assert payload["live_viewers_detail"] == "Contagem indisponível"
