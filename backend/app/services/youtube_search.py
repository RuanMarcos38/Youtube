from datetime import datetime, timedelta, timezone
import isodate
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from ..config import settings
from ..errors import raise_for_youtube_error


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


def discover_videos(keyword: str = "", region: str = "BR", max_results: int = 12, days: int = 14) -> list[dict]:
    youtube = _youtube_public_client()
    region = (region or settings.youtube_default_region).upper()
    max_results = max(1, min(max_results, 25))

    try:
        if keyword.strip():
            published_after = (datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 90)))).isoformat().replace("+00:00", "Z")
            search_response = youtube.search().list(
                part="snippet",
                q=keyword.strip(),
                type="video",
                order="viewCount",
                regionCode=region,
                publishedAfter=published_after,
                maxResults=max_results,
                safeSearch="moderate",
            ).execute()
            ids = [item["id"]["videoId"] for item in search_response.get("items", []) if item.get("id", {}).get("videoId")]
            if not ids:
                return []
            response = youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(ids),
                maxResults=max_results,
            ).execute()
        else:
            response = youtube.videos().list(
                part="snippet,statistics,contentDetails",
                chart="mostPopular",
                regionCode=region,
                maxResults=max_results,
            ).execute()
        return [_normalize_video(item) for item in response.get("items", [])]
    except HttpError as exc:
        raise_for_youtube_error(exc)
        raise
