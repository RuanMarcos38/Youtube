from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import isodate
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from ..errors import raise_for_youtube_error
from ..models import YouTubeConnection
from .youtube_oauth import get_credentials_for_user


FULL_SUBSCRIBERS_TARGET = 1000
FULL_WATCH_HOURS_TARGET = 4000
FULL_SHORTS_VIEWS_TARGET = 10_000_000
EARLY_SUBSCRIBERS_TARGET = 500
EARLY_WATCH_HOURS_TARGET = 3000
EARLY_SHORTS_VIEWS_TARGET = 3_000_000
EARLY_UPLOADS_TARGET = 3


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _duration_seconds(value: str | None) -> int:
    if not value:
        return 0
    try:
        return int(isodate.parse_duration(value).total_seconds())
    except Exception:
        return 0


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _thumbnail(snippet: dict) -> str:
    thumbnails = snippet.get("thumbnails", {})
    thumb = thumbnails.get("maxres") or thumbnails.get("standard") or thumbnails.get("high") or thumbnails.get("medium") or thumbnails.get("default") or {}
    return thumb.get("url", "")


def _normalize_video(item: dict) -> dict:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    content = item.get("contentDetails", {})
    video_id = item.get("id", "")
    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "thumbnail_url": _thumbnail(snippet),
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "published_at": snippet.get("publishedAt"),
        "view_count": _to_int(stats.get("viewCount")),
        "like_count": _to_int(stats.get("likeCount")),
        "comment_count": _to_int(stats.get("commentCount")),
        "duration_seconds": _duration_seconds(content.get("duration")),
    }


def _progress(value: float, target: float) -> float:
    if target <= 0:
        return 0.0
    return round(min(100.0, max(0.0, (value / target) * 100)), 1)


def _analytics_value(response: dict, index: int = 0) -> float | None:
    rows = response.get("rows") or []
    if not rows:
        return None
    first = rows[0]
    if not isinstance(first, list) or len(first) <= index:
        return None
    return _to_float(first[index])


def _analytics_summary(creds) -> dict:
    summary = {
        "analytics_available": False,
        "analytics_note": "YouTube Analytics não retornou dados para este canal.",
        "views_last_28d": None,
        "views_last_90d": None,
        "watch_hours_last_365d": None,
    }
    try:
        analytics = build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)
        today = date.today()
        last_28 = analytics.reports().query(
            ids="channel==MINE",
            startDate=(today - timedelta(days=28)).isoformat(),
            endDate=today.isoformat(),
            metrics="views",
        ).execute()
        last_90 = analytics.reports().query(
            ids="channel==MINE",
            startDate=(today - timedelta(days=90)).isoformat(),
            endDate=today.isoformat(),
            metrics="views",
        ).execute()
        last_365 = analytics.reports().query(
            ids="channel==MINE",
            startDate=(today - timedelta(days=365)).isoformat(),
            endDate=today.isoformat(),
            metrics="estimatedMinutesWatched",
        ).execute()
        minutes = _analytics_value(last_365)
        summary.update(
            {
                "analytics_available": True,
                "analytics_note": None,
                "views_last_28d": int(_analytics_value(last_28) or 0),
                "views_last_90d": int(_analytics_value(last_90) or 0),
                "watch_hours_last_365d": round((minutes or 0) / 60, 1),
            }
        )
    except Exception:
        # Many already-connected users have not granted the optional Analytics
        # scope yet. Keep the live dashboard available with Data API metrics.
        pass
    return summary


def _recent_uploads(youtube, uploads_playlist_id: str | None, max_results: int) -> list[dict]:
    if not uploads_playlist_id:
        return []
    response = youtube.playlistItems().list(
        part="contentDetails",
        playlistId=uploads_playlist_id,
        maxResults=max(1, min(max_results, 25)),
    ).execute()
    ids = [
        item.get("contentDetails", {}).get("videoId")
        for item in response.get("items", [])
        if item.get("contentDetails", {}).get("videoId")
    ]
    if not ids:
        return []
    videos = youtube.videos().list(
        part="snippet,statistics,contentDetails",
        id=",".join(ids),
        maxResults=len(ids),
    ).execute()
    normalized = [_normalize_video(item) for item in videos.get("items", [])]
    return sorted(normalized, key=lambda item: item["view_count"], reverse=True)


def _monetization_payload(subscribers: int, recent_videos: list[dict], analytics: dict) -> dict:
    now = datetime.now(timezone.utc)
    recent_90 = [
        item for item in recent_videos
        if (published := _parse_datetime(item.get("published_at"))) and published >= now - timedelta(days=90)
    ]
    shorts_views_90d_estimate = sum(item["view_count"] for item in recent_90 if item["duration_seconds"] <= 90)
    watch_hours = analytics.get("watch_hours_last_365d")
    early_watch_ok = watch_hours is not None and watch_hours >= EARLY_WATCH_HOURS_TARGET
    full_watch_ok = watch_hours is not None and watch_hours >= FULL_WATCH_HOURS_TARGET
    early_shorts_ok = shorts_views_90d_estimate >= EARLY_SHORTS_VIEWS_TARGET
    full_shorts_ok = shorts_views_90d_estimate >= FULL_SHORTS_VIEWS_TARGET
    early_eligible = subscribers >= EARLY_SUBSCRIBERS_TARGET and len(recent_90) >= EARLY_UPLOADS_TARGET and (early_watch_ok or early_shorts_ok)
    full_eligible = subscribers >= FULL_SUBSCRIBERS_TARGET and (full_watch_ok or full_shorts_ok)
    subscriber_progress = _progress(subscribers, FULL_SUBSCRIBERS_TARGET)
    watch_hours_progress = _progress(watch_hours or 0, FULL_WATCH_HOURS_TARGET)
    shorts_views_progress = _progress(shorts_views_90d_estimate, FULL_SHORTS_VIEWS_TARGET)
    content_progress = max(watch_hours_progress, shorts_views_progress)
    return {
        "subscriber_target_early": EARLY_SUBSCRIBERS_TARGET,
        "subscriber_target_full": FULL_SUBSCRIBERS_TARGET,
        "watch_hours_target_early": EARLY_WATCH_HOURS_TARGET,
        "watch_hours_target_full": FULL_WATCH_HOURS_TARGET,
        "shorts_views_target_early": EARLY_SHORTS_VIEWS_TARGET,
        "shorts_views_target_full": FULL_SHORTS_VIEWS_TARGET,
        "uploads_target_early": EARLY_UPLOADS_TARGET,
        "recent_public_uploads_90d": len(recent_90),
        "shorts_views_90d_estimate": shorts_views_90d_estimate,
        "watch_hours_last_365d": watch_hours,
        "subscriber_progress_full": subscriber_progress,
        "watch_hours_progress_full": watch_hours_progress,
        "shorts_views_progress_full": shorts_views_progress,
        "eligible_early_estimate": early_eligible,
        "eligible_full_estimate": full_eligible,
        "near_monetization": full_eligible or (subscriber_progress >= 80 and content_progress >= 80),
    }


def _alerts(channel_title: str, recent_videos: list[dict], monetization: dict, analytics: dict) -> list[dict]:
    alerts: list[dict] = []
    if recent_videos:
        top = recent_videos[0]
        avg_views = sum(item["view_count"] for item in recent_videos) / max(1, len(recent_videos))
        if top["view_count"] >= 100_000:
            alerts.append({
                "kind": "success",
                "title": "Vídeo em forte destaque",
                "detail": f"{top['title']} passou de 100 mil visualizações.",
            })
        elif top["view_count"] >= max(10_000, avg_views * 1.5):
            alerts.append({
                "kind": "info",
                "title": "Vídeo acima da média recente",
                "detail": f"{top['title']} está puxando o desempenho do canal.",
            })

    if monetization["eligible_full_estimate"]:
        alerts.append({
            "kind": "success",
            "title": "Canal em zona de monetização",
            "detail": "As métricas disponíveis indicam aderência aos principais marcos do YPP.",
        })
    elif monetization["near_monetization"]:
        alerts.append({
            "kind": "warning",
            "title": "Canal perto da monetização",
            "detail": "O painel detectou avanço relevante rumo aos marcos de inscritos, horas ou Shorts views.",
        })

    if not analytics.get("analytics_available"):
        alerts.append({
            "kind": "info",
            "title": "Analytics opcional pendente",
            "detail": "Watch hours oficiais dependem do YouTube Analytics/Studio; o painel segue com metricas publicas e estimativas recentes.",
        })

    if not alerts:
        alerts.append({
            "kind": "info",
            "title": "Painel ao vivo ativo",
            "detail": f"As métricas públicas do canal {channel_title or 'conectado'} foram atualizadas.",
        })
    return alerts[:5]


def get_live_channel_metrics(db: Session, user_id: int, max_results: int = 12) -> dict:
    connection = db.query(YouTubeConnection).filter(YouTubeConnection.user_id == user_id).first()
    if not connection or not connection.token_json:
        raise RuntimeError("YouTube não está conectado para este perfil.")

    creds = get_credentials_for_user(db, user_id)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    try:
        response = youtube.channels().list(
            part="snippet,statistics,contentDetails",
            mine=True,
            maxResults=1,
        ).execute()
    except HttpError as exc:
        raise_for_youtube_error(exc)
        raise

    items = response.get("items", [])
    if not items:
        raise RuntimeError("Nenhum canal do YouTube foi encontrado para esta conta.")

    channel = items[0]
    snippet = channel.get("snippet", {})
    stats = channel.get("statistics", {})
    content = channel.get("contentDetails", {})
    uploads_playlist_id = content.get("relatedPlaylists", {}).get("uploads")
    try:
        recent_videos = _recent_uploads(youtube, uploads_playlist_id, max_results)
    except HttpError as exc:
        raise_for_youtube_error(exc)
        raise
    analytics = _analytics_summary(creds)
    subscriber_count = 0 if stats.get("hiddenSubscriberCount") else _to_int(stats.get("subscriberCount"))
    monetization = _monetization_payload(subscriber_count, recent_videos, analytics)
    top_video = recent_videos[0] if recent_videos else None

    return {
        "channel_id": channel.get("id"),
        "channel_title": snippet.get("title") or connection.channel_title,
        "channel_thumbnail_url": _thumbnail(snippet),
        "channel_custom_url": snippet.get("customUrl"),
        "published_at": snippet.get("publishedAt"),
        "subscriber_count": subscriber_count,
        "hidden_subscriber_count": bool(stats.get("hiddenSubscriberCount")),
        "view_count": _to_int(stats.get("viewCount")),
        "video_count": _to_int(stats.get("videoCount")),
        "recent_videos": recent_videos,
        "top_video": top_video,
        "alerts": _alerts(snippet.get("title") or "", recent_videos, monetization, analytics),
        "monetization": monetization,
        "analytics_available": analytics["analytics_available"],
        "analytics_note": analytics["analytics_note"],
        "views_last_28d": analytics["views_last_28d"],
        "views_last_90d": analytics["views_last_90d"],
        "watch_hours_last_365d": analytics["watch_hours_last_365d"],
        "refreshed_at": datetime.now(timezone.utc),
    }
