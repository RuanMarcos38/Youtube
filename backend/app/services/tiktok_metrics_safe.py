from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import Session

from .tiktok_metrics import (
    USER_INFO_URL,
    _alerts,
    _load_history,
    _local_post_summary,
    _monetization,
    _period_history,
    _recent_videos,
    _release_read_transaction,
    _safe_int,
    get_tiktok_metrics as _get_full_metrics,
)
from .tiktok_oauth import get_access_token, token_scopes


FULL_METRIC_SCOPES = {"user.info.stats", "video.list"}
VIDEO_METRIC_SCOPE = "video.list"


def _basic_profile(access_token: str) -> dict:
    """Read only fields covered by user.info.basic.

    This intentionally avoids follower_count/following_count/likes_count while
    user.info.stats is not granted, preventing the OAuth scope regression that
    used to send users to TikTok's generic `scope` error page.
    """
    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                USER_INFO_URL,
                params={"fields": "open_id,display_name,avatar_url"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        payload = response.json()
    except (httpx.RequestError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    error = payload.get("error") or {}
    if response.is_error or error.get("code") not in {None, "ok", 0}:
        return {}
    return (payload.get("data") or {}).get("user") or {}


def _local_only_result(db: Session, user_id: int, days: int, *, detail: str) -> dict:
    local = _local_post_summary(db, user_id)
    history = _period_history(_load_history(db, user_id), days)
    _release_read_transaction(db)
    now = datetime.now(timezone.utc).isoformat()
    alerts = [
        {
            "kind": "warning",
            "title": "Métricas oficiais limitadas pelo TikTok",
            "detail": detail,
        },
        {
            "kind": "info",
            "title": "Operação local continua ativa",
            "detail": "Fila, processamentos, publicações confirmadas, falhas e pausas continuam sendo acompanhados pelo ShortsFlow sem alterar a conexão atual.",
        },
    ]
    alerts.extend(_alerts(local, {}, {}, [], 0))
    return {
        "available": True,
        "metrics_authorized": False,
        "reason": detail,
        "refreshed_at": now,
        "period_days": days,
        "profile": {
            "display_name": "",
            "avatar_url": "",
            "followers": 0,
            "following": 0,
            "likes_total": 0,
            "video_count": 0,
        },
        "period": {
            "videos": 0,
            "views": 0,
            "likes": 0,
            "comments": 0,
            "shares": 0,
            "engagement_total": 0,
            "engagement_rate": 0.0,
            "avg_views_per_video": 0.0,
        },
        "growth": {
            "followers_delta": 0,
            "likes_total_delta": 0,
            "video_count_delta": 0,
            "views_period_delta": 0,
        },
        "top_videos": [],
        "history": history,
        "local_publications": local,
        "monetization": {
            "official_revenue_available": False,
            "official_revenue": None,
            "currency": "BRL",
            "creator_rewards_min_duration_sec": 60,
            "duration_eligible_videos": 0,
            "duration_ineligible_videos": 0,
            "note": "O TikTok não expõe a receita oficial do Creator Rewards por esta API. Os números de desempenho permanecem indisponíveis até o app ter os escopos de Display API aprovados.",
        },
        "alerts": alerts[:8],
    }


def _video_list_result(db: Session, user_id: int, days: int) -> dict:
    local = _local_post_summary(db, user_id)
    history = _period_history(_load_history(db, user_id), days)
    _release_read_transaction(db)

    access_token = get_access_token(db, user_id)
    profile = _basic_profile(access_token)
    videos = _recent_videos(access_token)
    cutoff = None if days <= 0 else int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    period_videos = [
        item for item in videos
        if cutoff is None or _safe_int(item.get("create_time")) >= cutoff
    ]

    def total(field: str) -> int:
        return sum(_safe_int(item.get(field)) for item in period_videos)

    normalized_videos = [
        {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or item.get("video_description") or "Vídeo TikTok"),
            "create_time": _safe_int(item.get("create_time")),
            "duration": _safe_int(item.get("duration")),
            "cover_image_url": str(item.get("cover_image_url") or ""),
            "share_url": str(item.get("share_url") or ""),
            "view_count": _safe_int(item.get("view_count")),
            "like_count": _safe_int(item.get("like_count")),
            "comment_count": _safe_int(item.get("comment_count")),
            "share_count": _safe_int(item.get("share_count")),
        }
        for item in period_videos
    ]
    normalized_videos.sort(key=lambda item: item["view_count"], reverse=True)

    views = total("view_count")
    likes = total("like_count")
    comments = total("comment_count")
    shares = total("share_count")
    engagement_total = likes + comments + shares
    period = {
        "videos": len(period_videos),
        "views": views,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "engagement_total": engagement_total,
        "engagement_rate": round((engagement_total / views * 100.0), 2) if views > 0 else 0.0,
        "avg_views_per_video": round(views / len(period_videos), 1) if period_videos else 0.0,
    }
    monetization = _monetization(period_videos)
    alerts = [
        {
            "kind": "info",
            "title": "Métricas de vídeos ativas",
            "detail": "Visualizações, curtidas, comentários e compartilhamentos vêm da Display API. Seguidores e totais do perfil aguardam o escopo user.info.stats do app.",
        }
    ]
    alerts.extend(_alerts(local, period, {}, normalized_videos, monetization["duration_eligible_videos"]))
    now = datetime.now(timezone.utc).isoformat()
    return {
        "available": True,
        "metrics_authorized": False,
        "reason": "video.list autorizado; user.info.stats ainda não foi liberado pelo TikTok para esta conexão.",
        "refreshed_at": now,
        "period_days": days,
        "profile": {
            "display_name": str(profile.get("display_name") or ""),
            "avatar_url": str(profile.get("avatar_url") or ""),
            "followers": 0,
            "following": 0,
            "likes_total": 0,
            "video_count": 0,
        },
        "period": period,
        "growth": {
            "followers_delta": 0,
            "likes_total_delta": 0,
            "video_count_delta": 0,
            "views_period_delta": 0,
        },
        "top_videos": normalized_videos[:10],
        "history": history,
        "local_publications": local,
        "monetization": monetization,
        "alerts": alerts[:8],
    }


def get_tiktok_metrics(db: Session, user_id: int, *, days: int = 30) -> dict:
    """Return the richest safe TikTok dashboard available for the current token.

    Crucially, this function never forces a new OAuth request. That preserves the
    working publishing credential and prevents the TikTok `scope` authorization
    page from returning when Display API scopes are not approved for the app.
    """
    days = max(0, min(3650, int(days)))
    scopes = token_scopes(db, user_id)

    if FULL_METRIC_SCOPES.issubset(scopes):
        try:
            return _get_full_metrics(db, user_id, days=days)
        except RuntimeError as exc:
            message = str(exc)
            if "scope" not in message.lower() and "autoriza" not in message.lower():
                raise
            # Token metadata can occasionally be stale after TikTok changes app
            # permissions. Fall back without destroying or replacing the token.

    if VIDEO_METRIC_SCOPE in scopes:
        try:
            return _video_list_result(db, user_id, days)
        except RuntimeError as exc:
            return _local_only_result(
                db,
                user_id,
                days,
                detail=f"A Display API não liberou as métricas de vídeo nesta sessão: {exc}",
            )

    return _local_only_result(
        db,
        user_id,
        days,
        detail=(
            "A conexão de publicação continua válida, mas o app TikTok ainda não possui video.list/user.info.stats aprovados. "
            "O ShortsFlow não solicitará esses escopos automaticamente para não provocar novamente a página de erro 'scope'."
        ),
    )
