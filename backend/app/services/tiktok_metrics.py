from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from ..models import SystemSetting, TikTokPost
from .tiktok_oauth import get_access_token, metrics_authorized


USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
VIDEO_LIST_URL = "https://open.tiktokapis.com/v2/video/list/"
HISTORY_PREFIX = "tiktok.metrics.history."
SNAPSHOT_MINUTES = 15
MAX_SNAPSHOTS = 240


def _history_key(user_id: int) -> str:
    return f"{HISTORY_PREFIX}{int(user_id)}"


def _request_error(response: httpx.Response, payload: dict, fallback: str) -> RuntimeError:
    error = payload.get("error") or {}
    code = str(error.get("code") or "unknown")
    message = str(error.get("message") or response.text or fallback)
    return RuntimeError(f"TikTok ({code}): {message}")


def _user_stats(access_token: str) -> dict:
    fields = "open_id,display_name,avatar_url,follower_count,following_count,likes_count,video_count"
    with httpx.Client(timeout=25.0) as client:
        response = client.get(
            USER_INFO_URL,
            params={"fields": fields},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    payload = response.json()
    error = payload.get("error") or {}
    if response.is_error or error.get("code") not in {None, "ok", 0}:
        raise _request_error(response, payload, "Falha ao consultar estatísticas do perfil TikTok.")
    return (payload.get("data") or {}).get("user") or {}


def _recent_videos(access_token: str, *, max_pages: int = 5) -> list[dict]:
    fields = "id,create_time,title,video_description,duration,cover_image_url,share_url,view_count,like_count,comment_count,share_count"
    videos: list[dict] = []
    cursor = None
    with httpx.Client(timeout=30.0) as client:
        for _ in range(max(1, min(10, max_pages))):
            body: dict[str, int] = {"max_count": 20}
            if cursor is not None:
                body["cursor"] = int(cursor)
            response = client.post(
                VIDEO_LIST_URL,
                params={"fields": fields},
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            payload = response.json()
            error = payload.get("error") or {}
            if response.is_error or error.get("code") not in {None, "ok", 0}:
                raise _request_error(response, payload, "Falha ao listar vídeos do TikTok.")
            data = payload.get("data") or {}
            page = data.get("videos") or []
            videos.extend(item for item in page if isinstance(item, dict))
            if not data.get("has_more"):
                break
            cursor = data.get("cursor")
            if cursor is None:
                break
    return videos


def _load_history(db: Session, user_id: int) -> list[dict]:
    row = db.get(SystemSetting, _history_key(user_id))
    if not row or not row.value:
        return []
    try:
        value = json.loads(row.value)
        return value if isinstance(value, list) else []
    except Exception:
        return []


def _store_snapshot(db: Session, user_id: int, snapshot: dict) -> list[dict]:
    history = _load_history(db, user_id)
    now = datetime.now(timezone.utc)
    should_add = True
    if history:
        try:
            last = datetime.fromisoformat(str(history[-1].get("captured_at") or "").replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            should_add = now - last >= timedelta(minutes=SNAPSHOT_MINUTES)
        except Exception:
            pass
    if should_add:
        history.append(snapshot)
    history = history[-MAX_SNAPSHOTS:]
    row = db.get(SystemSetting, _history_key(user_id))
    encoded = json.dumps(history, ensure_ascii=False)
    if row is None:
        db.add(SystemSetting(key=_history_key(user_id), value=encoded, secret=False))
    else:
        row.value = encoded
        row.secret = False
    db.commit()
    return history


def _period_history(history: list[dict], days: int) -> list[dict]:
    if days <= 0:
        return history[-120:]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    result = []
    for item in history:
        try:
            captured = datetime.fromisoformat(str(item.get("captured_at") or "").replace("Z", "+00:00"))
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=timezone.utc)
            if captured >= cutoff:
                result.append(item)
        except Exception:
            continue
    return result[-120:]


def _local_post_summary(db: Session, user_id: int) -> dict:
    rows = db.query(TikTokPost).filter(TikTokPost.user_id == user_id).all()
    counts: dict[str, int] = {}
    for row in rows:
        counts[row.status] = counts.get(row.status, 0) + 1
    return {
        "total_attempts": len(rows),
        "published_confirmed": counts.get("published", 0),
        "processing": counts.get("processing", 0) + counts.get("submitted", 0) + counts.get("uploading", 0),
        "failed": counts.get("failed", 0),
        "paused_limit": counts.get("paused_limit", 0),
        "queued": counts.get("queued", 0),
    }


def get_tiktok_metrics(db: Session, user_id: int, *, days: int = 30) -> dict:
    days = max(0, min(3650, int(days)))
    local = _local_post_summary(db, user_id)
    if not metrics_authorized(db, user_id):
        return {
            "available": False,
            "metrics_authorized": False,
            "reason": "Autorize os escopos user.info.stats e video.list para liberar métricas reais do TikTok.",
            "local_publications": local,
            "history": _period_history(_load_history(db, user_id), days),
        }

    access_token = get_access_token(db, user_id)
    profile = _user_stats(access_token)
    videos = _recent_videos(access_token)
    cutoff = None if days <= 0 else int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    period_videos = [
        item for item in videos
        if cutoff is None or int(item.get("create_time") or 0) >= cutoff
    ]

    def total(field: str) -> int:
        return sum(int(item.get(field) or 0) for item in period_videos)

    normalized_videos = [
        {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or item.get("video_description") or "Vídeo TikTok"),
            "create_time": int(item.get("create_time") or 0),
            "cover_image_url": str(item.get("cover_image_url") or ""),
            "share_url": str(item.get("share_url") or ""),
            "view_count": int(item.get("view_count") or 0),
            "like_count": int(item.get("like_count") or 0),
            "comment_count": int(item.get("comment_count") or 0),
            "share_count": int(item.get("share_count") or 0),
        }
        for item in period_videos
    ]
    normalized_videos.sort(key=lambda item: item["view_count"], reverse=True)

    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "followers": int(profile.get("follower_count") or 0),
        "following": int(profile.get("following_count") or 0),
        "likes_total": int(profile.get("likes_count") or 0),
        "video_count": int(profile.get("video_count") or 0),
        "views_period": total("view_count"),
        "likes_period": total("like_count"),
        "comments_period": total("comment_count"),
        "shares_period": total("share_count"),
    }
    history = _store_snapshot(db, user_id, snapshot)
    return {
        "available": True,
        "metrics_authorized": True,
        "refreshed_at": snapshot["captured_at"],
        "period_days": days,
        "profile": {
            "display_name": str(profile.get("display_name") or ""),
            "avatar_url": str(profile.get("avatar_url") or ""),
            "followers": snapshot["followers"],
            "following": snapshot["following"],
            "likes_total": snapshot["likes_total"],
            "video_count": snapshot["video_count"],
        },
        "period": {
            "videos": len(period_videos),
            "views": snapshot["views_period"],
            "likes": snapshot["likes_period"],
            "comments": snapshot["comments_period"],
            "shares": snapshot["shares_period"],
        },
        "top_videos": normalized_videos[:10],
        "history": _period_history(history, days),
        "local_publications": local,
    }
