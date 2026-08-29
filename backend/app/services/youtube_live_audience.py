from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from ..errors import google_error_reason, raise_for_youtube_error
from ..models import YouTubeConnection
from .youtube_oauth import get_credentials_for_user


LIVE_AUDIENCE_ZERO_REASONS = {
    "liveStreamingNotEnabled",
}

LIVE_AUDIENCE_UNAVAILABLE_REASONS = {
    "insufficientLivePermissions",
}


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _sum_concurrent_viewers(items: list[dict]) -> int:
    return sum(
        _to_int(item.get("liveStreamingDetails", {}).get("concurrentViewers"))
        for item in items
    )


def _payload(*, concurrent_viewers: int = 0, active_live_broadcasts: int = 0, available: bool = True) -> dict:
    return {
        "concurrent_viewers": max(0, concurrent_viewers),
        "active_live_broadcasts": max(0, active_live_broadcasts),
        "available": available,
        "refreshed_at": datetime.now(timezone.utc),
    }


def get_live_audience(db: Session, user_id: int) -> dict:
    """Return the current concurrent audience for active broadcasts owned by the connected channel.

    YouTube exposes an exact current viewer count only for active live broadcasts.
    It does not expose a channel-wide list/count of people currently watching ordinary uploaded videos.
    """
    connection = db.query(YouTubeConnection).filter(YouTubeConnection.user_id == user_id).first()
    if not connection or not connection.token_json:
        raise RuntimeError("YouTube não está conectado para este perfil.")

    creds = get_credentials_for_user(db, user_id)
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

    try:
        broadcasts = youtube.liveBroadcasts().list(
            part="id",
            broadcastStatus="active",
            broadcastType="all",
            maxResults=50,
        ).execute()
    except HttpError as exc:
        reason, _ = google_error_reason(exc)
        if reason in LIVE_AUDIENCE_ZERO_REASONS:
            # A channel without live-streaming enabled cannot have an active
            # broadcast, so the truthful current live audience is zero rather
            # than an unavailable/blank metric.
            return _payload()
        if reason in LIVE_AUDIENCE_UNAVAILABLE_REASONS:
            return _payload(available=False)
        raise_for_youtube_error(exc)
        raise

    broadcast_ids = [
        str(item.get("id") or "").strip()
        for item in broadcasts.get("items", [])
        if str(item.get("id") or "").strip()
    ]
    if not broadcast_ids:
        return _payload()

    try:
        videos = youtube.videos().list(
            part="liveStreamingDetails",
            id=",".join(broadcast_ids),
            maxResults=min(50, len(broadcast_ids)),
        ).execute()
    except HttpError as exc:
        raise_for_youtube_error(exc)
        raise

    return _payload(
        concurrent_viewers=_sum_concurrent_viewers(videos.get("items", [])),
        active_live_broadcasts=len(broadcast_ids),
    )
