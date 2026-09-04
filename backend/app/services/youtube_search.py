from datetime import datetime, timedelta, timezone

import isodate
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..config import settings
from ..errors import raise_for_youtube_error

MIN_SOURCE_DURATION_SECONDS = 50 * 60
SEARCH_PAGE_SIZE = 50
MAX_SEARCH_PAGES = 3


def _youtube_public_client():
    if not settings.youtube_api_key:
        raise RuntimeError("YOUTUBE_API_KEY is not configured")
    return build("youtube", "v3", developerKey=settings.youtube_api_key, cache_discovery=False)


def _to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _duration_seconds(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(isodate.parse_duration(value).total_seconds())
    except Exception:
        return 0


def _normalize_video(item: dict) -> dict:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    content = item.get("contentDetails", {})
    thumbnails = snippet.get("thumbnails", {})
    thumb = thumbnails.get("high") or thumbnails.get("medium") or thumbnails.get("default") or {}
    video_id = item.get("id", "")
    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "channel_title": snippet.get("channelTitle", ""),
        "thumbnail_url": thumb.get("url", ""),
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "published_at": snippet.get("publishedAt"),
        "view_count": _to_int(stats.get("viewCount")),
        "like_count": _to_int(stats.get("likeCount")),
        "comment_count": _to_int(stats.get("commentCount")),
        "duration_seconds": _duration_seconds(content.get("duration")),
    }


def _published_sort_key(video: dict) -> str:
    return str(video.get("published_at") or "")


def discover_videos(keyword: str = "", region: str = "BR", max_results: int = 12, days: int = 14) -> list[dict]:
    """Return newly published long-form videos suitable for Shorts extraction.

    YouTube's ``videoDuration=long`` filter only guarantees videos longer than
    20 minutes, so the exact 50-minute requirement is enforced after fetching
    contentDetails. Results are ordered by publication date, not by lifetime
    view count, so the workspace surfaces fresh source material first.
    """
    youtube = _youtube_public_client()
    region = (region or settings.youtube_default_region).upper()
    max_results = max(1, min(max_results, 25))
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 90)))
    ).isoformat().replace("+00:00", "Z")

    eligible: dict[str, dict] = {}
    page_token: str | None = None

    try:
        for _ in range(MAX_SEARCH_PAGES):
            params = {
                "part": "snippet",
                "type": "video",
                "order": "date",
                "regionCode": region,
                "publishedAfter": published_after,
                "videoDuration": "long",
                "maxResults": SEARCH_PAGE_SIZE,
                "safeSearch": "moderate",
            }
            if keyword.strip():
                params["q"] = keyword.strip()
            if page_token:
                params["pageToken"] = page_token

            search_response = youtube.search().list(**params).execute()
            ids = [
                item.get("id", {}).get("videoId")
                for item in search_response.get("items", [])
                if item.get("id", {}).get("videoId")
            ]
            if ids:
                response = youtube.videos().list(
                    part="snippet,statistics,contentDetails",
                    id=",".join(ids),
                    maxResults=SEARCH_PAGE_SIZE,
                ).execute()
                for item in response.get("items", []):
                    video = _normalize_video(item)
                    if video["duration_seconds"] < MIN_SOURCE_DURATION_SECONDS:
                        continue
                    if video["video_id"]:
                        eligible[video["video_id"]] = video

            if len(eligible) >= max_results:
                break
            page_token = search_response.get("nextPageToken")
            if not page_token:
                break

        ordered = sorted(eligible.values(), key=_published_sort_key, reverse=True)
        return ordered[:max_results]
    except HttpError as exc:
        raise_for_youtube_error(exc)
        raise
