from app.services import youtube_search


class _Request:
    def __init__(self, payload):
        self.payload = payload

    def execute(self):
        return self.payload


class _SearchResource:
    def __init__(self):
        self.calls = []

    def list(self, **kwargs):
        self.calls.append(kwargs)
        token = kwargs.get("pageToken")
        pages = {
            None: {"items": [{"id": {"videoId": "video000001"}}], "nextPageToken": "p2"},
            "p2": {"items": [{"id": {"videoId": "video000002"}}], "nextPageToken": "p3"},
            "p3": {"items": [{"id": {"videoId": "video000003"}}], "nextPageToken": "p4"},
            "p4": {"items": [{"id": {"videoId": "video000004"}}]},
        }
        return _Request(pages[token])


class _VideosResource:
    def list(self, **kwargs):
        ids = [item for item in kwargs.get("id", "").split(",") if item]
        published = {
            "video000001": "2026-09-01T00:00:00Z",
            "video000002": "2026-09-02T00:00:00Z",
            "video000003": "2026-09-03T00:00:00Z",
            "video000004": "2026-09-04T00:00:00Z",
        }
        items = [
            {
                "id": video_id,
                "snippet": {
                    "title": video_id,
                    "channelTitle": "Canal",
                    "publishedAt": published[video_id],
                    "thumbnails": {"default": {"url": "https://example.com/thumb.jpg"}},
                },
                "statistics": {"viewCount": "10", "likeCount": "1", "commentCount": "0"},
                "contentDetails": {"duration": "PT1H"},
            }
            for video_id in ids
        ]
        return _Request({"items": items})


class _FakeYouTube:
    def __init__(self):
        self.search_resource = _SearchResource()
        self.videos_resource = _VideosResource()

    def search(self):
        return self.search_resource

    def videos(self):
        return self.videos_resource


def test_discovery_does_not_stop_when_visible_result_limit_is_reached(monkeypatch):
    fake = _FakeYouTube()
    youtube_search._SEARCH_CACHE.clear()
    monkeypatch.setattr(youtube_search, "_youtube_public_client", lambda: fake)

    result = youtube_search.discover_videos(keyword="teste", region="BR", max_results=3, days=14)

    assert len(fake.search_resource.calls) == 4
    assert [item["video_id"] for item in result] == ["video000004", "video000003", "video000002"]
    first_call = fake.search_resource.calls[0]
    assert first_call["maxResults"] == 50
    assert first_call["safeSearch"] == "none"
    assert first_call["order"] == "relevance"


def test_direct_youtube_url_is_resolved_without_ranked_search(monkeypatch):
    fake = _FakeYouTube()
    youtube_search._SEARCH_CACHE.clear()
    monkeypatch.setattr(youtube_search, "_youtube_public_client", lambda: fake)

    result = youtube_search.discover_videos(
        keyword="https://www.youtube.com/watch?v=video000004",
        region="BR",
        max_results=10,
        days=14,
    )

    assert [item["video_id"] for item in result] == ["video000004"]
    assert fake.search_resource.calls == []
