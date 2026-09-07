from datetime import datetime, timedelta, timezone
import re
import time

import isodate
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from ..config import settings
from ..errors import raise_for_youtube_error

MIN_SOURCE_DURATION_SECONDS = 50 * 60
SEARCH_PAGE_SIZE = 50
# The previous implementation stopped after only 3 pages and also stopped as
# soon as it had enough results for the visible list. That made valid videos
# disappear from later YouTube pages. Scan a much wider result window and only
# apply the UI result limit after all scanned pages have been merged.
MAX_SEARCH_PAGES = 20
MAX_RETURNED_RESULTS = 500
SEARCH_CACHE_TTL_SECONDS = 15 * 60

_SEARCH_CACHE: dict[tuple[str, str, int, int], tuple[float, list[dict]]] = {}


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


def get_video_duration_seconds(video_id: str) -> int:
    """Fetch only contentDetails so usage limits are enforced server-side.

    This intentionally does not trust the browser for billing/usage metadata.
    """
    youtube = _youtube_public_client()
    try:
        response = youtube.videos().list(part="contentDetails", id=video_id, maxResults=1).execute()
        items = response.get("items", [])
        if not items:
            return 0
        return _duration_seconds(items[0].get("contentDetails", {}).get("duration"))
    except HttpError as exc:
        raise_for_youtube_error(exc)
        raise


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


def _extract_direct_video_id(keyword: str) -> str | None:
    value = (keyword or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    patterns = (
        r"(?:youtube\.com/watch\?[^\s]*v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
    )
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _fetch_video_details(youtube, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    response = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        id=",".join(ids[:SEARCH_PAGE_SIZE]),
        maxResults=SEARCH_PAGE_SIZE,
    ).execute()
    return response.get("items", [])


def _cache_get(key: tuple[str, str, int, int]) -> list[dict] | None:
    cached = _SEARCH_CACHE.get(key)
    if not cached:
        return None
    created_at, videos = cached
    if time.monotonic() - created_at > SEARCH_CACHE_TTL_SECONDS:
        _SEARCH_CACHE.pop(key, None)
        return None
    return [dict(video) for video in videos]


def _cache_put(key: tuple[str, str, int, int], videos: list[dict]) -> None:
    if len(_SEARCH_CACHE) >= 50:
        oldest_key = min(_SEARCH_CACHE, key=lambda item: _SEARCH_CACHE[item][0])
        _SEARCH_CACHE.pop(oldest_key, None)
    _SEARCH_CACHE[key] = (time.monotonic(), [dict(video) for video in videos])


def discover_videos(keyword: str = "", region: str = "BR", max_results: int = 100, days: int = 14) -> list[dict]:
    """Return the broadest API-visible set of eligible long-form videos.

    Important behavior:
    - preserves the existing >=50 minute source rule;
    - scans every configured YouTube result page instead of stopping after the
      first few eligible items;
    - uses relevance ordering during discovery because YouTube documents that
      alternate sort orders combined with date filters can yield smaller result
      sets;
    - removes the previous moderate SafeSearch restriction so public videos are
      not silently excluded by ShortsFlow;
    - still respects the selected region and date window;
    - deduplicates by YouTube video id and sorts the final list by publish date.
    """
    youtube = _youtube_public_client()
    region = (region or settings.youtube_default_region).upper()
    max_results = max(1, min(int(max_results), MAX_RETURNED_RESULTS))
    normalized_days = max(1, min(int(days), 90))
    query = (keyword or "").strip()
    cache_key = (query.casefold(), region, normalized_days, max_results)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    published_after = (
        datetime.now(timezone.utc) - timedelta(days=normalized_days)
    ).isoformat().replace("+00:00", "Z")

    eligible: dict[str, dict] = {}

    try:
        # Exact URL/video-id searches should never disappear because of YouTube
        # search ranking. Fetch the video directly first and then continue with
        # the normal discovery path when the keyword is not an exact id/url.
        direct_video_id = _extract_direct_video_id(query)
        if direct_video_id:
            for item in _fetch_video_details(youtube, [direct_video_id]):
                video = _normalize_video(item)
                if video["duration_seconds"] >= MIN_SOURCE_DURATION_SECONDS:
                    eligible[video["video_id"]] = video
            ordered = sorted(eligible.values(), key=_published_sort_key, reverse=True)
            result = ordered[:max_results]
            _cache_put(cache_key, result)
            return result

        page_token: str | None = None
        for _ in range(MAX_SEARCH_PAGES):
            params = {
                "part": "snippet",
                "type": "video",
                "order": "relevance",
                "regionCode": region,
                "publishedAfter": published_after,
                "videoDuration": "long",
                "maxResults": SEARCH_PAGE_SIZE,
                "safeSearch": "none",
            }
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token

            search_response = youtube.search().list(**params).execute()
            ids = list(
                dict.fromkeys(
                    item.get("id", {}).get("videoId")
                    for item in search_response.get("items", [])
                    if item.get("id", {}).get("videoId")
                )
            )
            for item in _fetch_video_details(youtube, ids):
                video = _normalize_video(item)
                if video["duration_seconds"] < MIN_SOURCE_DURATION_SECONDS:
                    continue
                if video["video_id"]:
                    eligible[video["video_id"]] = video

            # Never stop merely because the visible list already has enough
            # items. Continue following YouTube's pagination token so later
            # pages cannot be omitted by ShortsFlow.
            page_token = search_response.get("nextPageToken")
            if not page_token:
                break

        ordered = sorted(eligible.values(), key=_published_sort_key, reverse=True)
        result = ordered[:max_results]
        _cache_put(cache_key, result)
        return result
    except HttpError as exc:
        raise_for_youtube_error(exc)
        raise
