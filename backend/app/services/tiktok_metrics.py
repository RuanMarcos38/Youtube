from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from threading import Lock

import httpx
from sqlalchemy.orm import Session

from ..models import SystemSetting, TikTokPost
from .tiktok_oauth import get_access_token, metrics_authorized


USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
VIDEO_LIST_URL = "https://open.tiktokapis.com/v2/video/list/"
HISTORY_PREFIX = "tiktok.metrics.history."
SNAPSHOT_MINUTES = 60
MAX_SNAPSHOTS = 24 * 120
METRICS_CACHE_TTL_SECONDS = 55
_METRICS_CACHE: dict[tuple[int, int], tuple[float, dict]] = {}
_METRICS_CACHE_LOCK = Lock()


def _history_key(user_id: int) -> str:
    return f"{HISTORY_PREFIX}{int(user_id)}"


def _release_read_transaction(db: Session) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _safe_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _safe_payload(response: httpx.Response, fallback: str) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        status_code = int(response.status_code or 0)
        if status_code >= 500:
            raise RuntimeError(
                f"TikTok está temporariamente indisponível para métricas (HTTP {status_code}). A publicação continua independente do dashboard."
            ) from exc
        raise RuntimeError(
            f"TikTok retornou uma resposta inválida para métricas (HTTP {status_code or 'desconhecido'})."
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(fallback)
    return payload


def _request_error(response: httpx.Response, payload: dict, fallback: str) -> RuntimeError:
    error = payload.get("error") or {}
    code = str(error.get("code") or "unknown")
    message = str(error.get("message") or response.text or fallback)
    if code == "access_token_invalid":
        return RuntimeError("A sessão do TikTok expirou. Reconecte a conta para atualizar as métricas.")
    if code == "scope_not_authorized":
        return RuntimeError("O TikTok não autorizou os escopos de métricas desta conexão. Ative as métricas novamente.")
    if code == "rate_limit_exceeded" or response.status_code == 429:
        return RuntimeError("O TikTok limitou temporariamente as consultas de métricas. O envio de vídeos continua disponível.")
    return RuntimeError(f"TikTok ({code}): {message}")


def _user_stats(access_token: str) -> dict:
    fields = "open_id,display_name,avatar_url,follower_count,following_count,likes_count,video_count"
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                USER_INFO_URL,
                params={"fields": fields},
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.RequestError as exc:
        raise RuntimeError(
            "Não foi possível consultar as métricas do TikTok agora. A publicação continua disponível; tente o dashboard novamente em alguns instantes."
        ) from exc
    payload = _safe_payload(response, "Falha ao consultar estatísticas do perfil TikTok.")
    error = payload.get("error") or {}
    if response.is_error or error.get("code") not in {None, "ok", 0}:
        raise _request_error(response, payload, "Falha ao consultar estatísticas do perfil TikTok.")
    return (payload.get("data") or {}).get("user") or {}


def _recent_videos(access_token: str, *, max_pages: int = 5) -> list[dict]:
    fields = "id,create_time,title,video_description,duration,cover_image_url,share_url,view_count,like_count,comment_count,share_count"
    videos: list[dict] = []
    cursor = None
    try:
        with httpx.Client(timeout=25.0) as client:
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
                payload = _safe_payload(response, "Falha ao listar vídeos do TikTok.")
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
    except httpx.RequestError as exc:
        raise RuntimeError(
            "Não foi possível listar os vídeos do TikTok para métricas agora. A publicação continua disponível."
        ) from exc
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
        return history[-MAX_SNAPSHOTS:]
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
    return result[-MAX_SNAPSHOTS:]


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


def _growth(history: list[dict], current: dict) -> dict:
    if not history:
        return {
            "followers_delta": 0,
            "likes_total_delta": 0,
            "video_count_delta": 0,
            "views_period_delta": 0,
        }
    first = history[0]
    return {
        "followers_delta": _safe_int(current.get("followers")) - _safe_int(first.get("followers")),
        "likes_total_delta": _safe_int(current.get("likes_total")) - _safe_int(first.get("likes_total")),
        "video_count_delta": _safe_int(current.get("video_count")) - _safe_int(first.get("video_count")),
        "views_period_delta": _safe_int(current.get("views_period")) - _safe_int(first.get("views_period")),
    }


def _alerts(local: dict, period: dict, growth: dict, normalized_videos: list[dict], duration_eligible: int) -> list[dict]:
    alerts: list[dict] = []
    if local.get("paused_limit"):
        alerts.append({
            "kind": "warning",
            "title": "Fila TikTok pausada por limite",
            "detail": f"{local['paused_limit']} publicação(ões) aguardando liberação do TikTok.",
        })
    if local.get("failed"):
        alerts.append({
            "kind": "danger",
            "title": "Falhas de publicação",
            "detail": f"{local['failed']} tentativa(s) falharam. Revise os motivos antes de reenviar em lote.",
        })
    if local.get("processing"):
        alerts.append({
            "kind": "info",
            "title": "Publicações em processamento",
            "detail": f"{local['processing']} vídeo(s) aguardando processamento ou moderação do TikTok.",
        })
    if period.get("videos", 0) == 0:
        alerts.append({
            "kind": "warning",
            "title": "Nenhum vídeo no período",
            "detail": "Não há vídeos retornados pelo TikTok no período selecionado.",
        })
    elif period.get("engagement_rate", 0) >= 8:
        alerts.append({
            "kind": "success",
            "title": "Engajamento forte",
            "detail": f"Taxa de engajamento do período em {period['engagement_rate']:.1f}%.",
        })
    if growth.get("followers_delta", 0) > 0:
        alerts.append({
            "kind": "success",
            "title": "Crescimento de seguidores",
            "detail": f"+{growth['followers_delta']} seguidor(es) desde o primeiro snapshot do período.",
        })
    if normalized_videos:
        top = normalized_videos[0]
        avg_views = max(1.0, float(period.get("avg_views_per_video") or 0))
        if top.get("view_count", 0) >= avg_views * 2:
            alerts.append({
                "kind": "success",
                "title": "Vídeo acima da média",
                "detail": f"“{str(top.get('title') or 'Vídeo')[:80]}” está com desempenho de visualizações acima da média do período.",
            })
    if period.get("videos", 0) and duration_eligible == 0:
        alerts.append({
            "kind": "info",
            "title": "Creator Rewards: duração",
            "detail": "Nenhum vídeo retornado no período possui 60 segundos ou mais; a duração é apenas um dos requisitos de elegibilidade do Creator Rewards.",
        })
    return alerts[:8]


def _monetization(period_videos: list[dict]) -> dict:
    eligible = sum(1 for item in period_videos if _safe_int(item.get("duration")) >= 60)
    ineligible = len(period_videos) - eligible
    return {
        "official_revenue_available": False,
        "official_revenue": None,
        "currency": "BRL",
        "creator_rewards_min_duration_sec": 60,
        "duration_eligible_videos": eligible,
        "duration_ineligible_videos": ineligible,
        "note": (
            "A API pública usada pelo ShortsFlow não fornece o valor oficial pago pelo Creator Rewards. "
            "O painel mostra métricas oficiais de desempenho e elegibilidade por duração sem inventar receita. "
            "O valor financeiro oficial deve ser consultado no TikTok Studio/Creator Rewards."
        ),
    }


def _cached_metrics(user_id: int, days: int) -> dict | None:
    key = (int(user_id), int(days))
    now = time.monotonic()
    with _METRICS_CACHE_LOCK:
        cached = _METRICS_CACHE.get(key)
        if not cached:
            return None
        expires_at, value = cached
        if expires_at <= now:
            _METRICS_CACHE.pop(key, None)
            return None
        return json.loads(json.dumps(value))


def _store_metrics_cache(user_id: int, days: int, value: dict) -> None:
    with _METRICS_CACHE_LOCK:
        _METRICS_CACHE[(int(user_id), int(days))] = (
            time.monotonic() + METRICS_CACHE_TTL_SECONDS,
            json.loads(json.dumps(value)),
        )


def get_tiktok_metrics(db: Session, user_id: int, *, days: int = 30) -> dict:
    days = max(0, min(3650, int(days)))
    local = _local_post_summary(db, user_id)
    history_all = _load_history(db, user_id)
    period_history = _period_history(history_all, days)
    _release_read_transaction(db)

    cached = _cached_metrics(user_id, days)
    if cached:
        cached["local_publications"] = local
        cached["alerts"] = _alerts(
            local,
            cached.get("period") or {},
            cached.get("growth") or {},
            cached.get("top_videos") or [],
            _safe_int((cached.get("monetization") or {}).get("duration_eligible_videos")),
        )
        return cached

    if not metrics_authorized(db, user_id):
        result = {
            "available": False,
            "metrics_authorized": False,
            "reason": "Autorize os escopos user.info.stats e video.list no app TikTok para liberar métricas oficiais.",
            "refreshed_at": datetime.now(timezone.utc).isoformat(),
            "period_days": days,
            "profile": None,
            "period": None,
            "growth": {
                "followers_delta": 0,
                "likes_total_delta": 0,
                "video_count_delta": 0,
                "views_period_delta": 0,
            },
            "top_videos": [],
            "local_publications": local,
            "history": period_history,
            "monetization": {
                "official_revenue_available": False,
                "official_revenue": None,
                "currency": "BRL",
                "creator_rewards_min_duration_sec": 60,
                "duration_eligible_videos": 0,
                "duration_ineligible_videos": 0,
                "note": "A API pública não expõe o valor oficial do Creator Rewards; ative as métricas para acompanhar desempenho e elegibilidade.",
            },
            "alerts": _alerts(local, {}, {}, [], 0),
        }
        _store_metrics_cache(user_id, days, result)
        return result

    access_token = get_access_token(db, user_id)
    # get_access_token devolve qualquer conexão SQL ao pool antes destas chamadas externas.
    profile = _user_stats(access_token)
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
    engagement_rate = round((engagement_total / views * 100.0), 2) if views > 0 else 0.0
    avg_views = round(views / len(period_videos), 1) if period_videos else 0.0
    period = {
        "videos": len(period_videos),
        "views": views,
        "likes": likes,
        "comments": comments,
        "shares": shares,
        "engagement_total": engagement_total,
        "engagement_rate": engagement_rate,
        "avg_views_per_video": avg_views,
    }

    snapshot = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "followers": _safe_int(profile.get("follower_count")),
        "following": _safe_int(profile.get("following_count")),
        "likes_total": _safe_int(profile.get("likes_count")),
        "video_count": _safe_int(profile.get("video_count")),
        "views_period": views,
        "likes_period": likes,
        "comments_period": comments,
        "shares_period": shares,
    }
    history = _store_snapshot(db, user_id, snapshot)
    period_history = _period_history(history, days)
    growth = _growth(period_history, snapshot)
    monetization = _monetization(period_videos)
    alerts = _alerts(local, period, growth, normalized_videos, monetization["duration_eligible_videos"])

    result = {
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
        "period": period,
        "growth": growth,
        "top_videos": normalized_videos[:10],
        "history": period_history,
        "local_publications": local,
        "monetization": monetization,
        "alerts": alerts,
    }
    _store_metrics_cache(user_id, days, result)
    return result
