from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import Clip, Job, SourceVideo, SystemSetting, TikTokPost, User
from .billing import can_use_tool, ensure_plan
from .downloader import download_access_configured
from .ffmpeg_service import FFmpegError, ensure_ffmpeg, render_vertical_clip
from .plans import can_create_job
from .tiktok_oauth import get_connection_status as tiktok_connection_status, get_creator_info
from .tiktok_policy import apply_unaudited_public_block, clear_legacy_unaudited_state, recover_retryable_draft_uploads
from .youtube_oauth import get_connection_status as youtube_connection_status
from .youtube_search import discover_videos

AUTO_SETTING_PREFIX = "auto_mode:"
AUTO_JOB_PREFIX = "auto_job:"
DISCOVERY_INTERVAL_SECONDS = 12 * 60 * 60
MAX_CLEAN_PER_TICK = 5

DEFAULT_AUTO_CONFIG = {
    "enabled": False,
    "keyword": "marketing digital",
    "region": "BR",
    "days": 14,
    "min_views": 0,
    "min_likes": 0,
    "clips_per_source": 10,
    "daily_target": 15,
    "publish_youtube": True,
    "publish_tiktok": True,
    "publish_start_hour": 8,
    "publish_end_hour": 22,
    "timezone": "America/Sao_Paulo",
    "rights_confirmed": False,
    "music_usage_confirmed": False,
    "tiktok_privacy_level": "PUBLIC_TO_EVERYONE",
    "allow_comment": True,
    "allow_duet": False,
    "allow_stitch": False,
    "max_active_jobs": 2,
    "last_discovery_at": None,
    "last_run_at": None,
    "last_selected_video_id": None,
    "last_selected_video_title": None,
    "last_error": None,
}


def _setting_key(user_id: int) -> str:
    return f"{AUTO_SETTING_PREFIX}{user_id}"


def _job_marker_key(job_id: int) -> str:
    return f"{AUTO_JOB_PREFIX}{job_id}"


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_auto_config(db: Session, user_id: int) -> dict:
    config = dict(DEFAULT_AUTO_CONFIG)
    row = db.get(SystemSetting, _setting_key(user_id))
    if not row or not row.value:
        return config
    try:
        payload = json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return config
    if isinstance(payload, dict):
        config.update(payload)
    return _normalize_config(config)


def _normalize_config(payload: dict) -> dict:
    config = dict(DEFAULT_AUTO_CONFIG)
    config.update(payload or {})
    config["enabled"] = bool(config.get("enabled"))
    config["keyword"] = str(config.get("keyword") or "").strip()[:120]
    config["region"] = str(config.get("region") or "BR").strip().upper()[:2] or "BR"
    config["days"] = max(1, min(90, int(config.get("days") or 14)))
    config["min_views"] = max(0, int(config.get("min_views") or 0))
    config["min_likes"] = max(0, int(config.get("min_likes") or 0))
    config["clips_per_source"] = 10
    config["daily_target"] = max(1, min(15, int(config.get("daily_target") or 15)))
    config["publish_youtube"] = bool(config.get("publish_youtube", True))
    config["publish_tiktok"] = bool(config.get("publish_tiktok", True))
    config["publish_start_hour"] = max(0, min(23, int(config.get("publish_start_hour") or 8)))
    config["publish_end_hour"] = max(1, min(24, int(config.get("publish_end_hour") or 22)))
    if config["publish_end_hour"] <= config["publish_start_hour"]:
        config["publish_end_hour"] = min(24, config["publish_start_hour"] + 1)
    config["timezone"] = str(config.get("timezone") or "America/Sao_Paulo")[:64]
    try:
        ZoneInfo(config["timezone"])
    except Exception:
        config["timezone"] = "America/Sao_Paulo"
    config["rights_confirmed"] = bool(config.get("rights_confirmed"))
    config["music_usage_confirmed"] = bool(config.get("music_usage_confirmed"))
    config["tiktok_privacy_level"] = str(config.get("tiktok_privacy_level") or "PUBLIC_TO_EVERYONE")[:50]
    config["allow_comment"] = bool(config.get("allow_comment", True))
    config["allow_duet"] = bool(config.get("allow_duet", False))
    config["allow_stitch"] = bool(config.get("allow_stitch", False))
    config["max_active_jobs"] = max(1, min(2, int(config.get("max_active_jobs") or 2)))
    return config


def save_auto_config(db: Session, user_id: int, payload: dict) -> dict:
    current = load_auto_config(db, user_id)
    current.update(payload or {})
    config = _normalize_config(current)
    if config["enabled"] and not config["rights_confirmed"]:
        raise ValueError("Para ativar o modo automático, confirme que os vídeos pesquisados estão dentro dos seus direitos, licença ou autorização de reutilização.")
    if config["enabled"] and config["publish_tiktok"] and not config["music_usage_confirmed"]:
        raise ValueError("Para automatizar o TikTok, confirme uma única vez a declaração de uso de música exigida pela plataforma.")

    row = db.get(SystemSetting, _setting_key(user_id))
    encoded = json.dumps(config, ensure_ascii=False)
    if row is None:
        row = SystemSetting(key=_setting_key(user_id), value=encoded, secret=False)
        db.add(row)
    else:
        row.value = encoded
        row.secret = False
    db.commit()
    return config


def _auto_job_ids(db: Session, user_id: int) -> list[int]:
    rows = (
        db.query(SystemSetting)
        .filter(SystemSetting.key.like(f"{AUTO_JOB_PREFIX}%"), SystemSetting.value == str(user_id))
        .all()
    )
    ids: list[int] = []
    for row in rows:
        try:
            ids.append(int(row.key.split(":", 1)[1]))
        except (IndexError, ValueError):
            continue
    return ids


def _mark_auto_job(db: Session, job_id: int, user_id: int) -> None:
    key = _job_marker_key(job_id)
    row = db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value=str(user_id), secret=False))
    else:
        row.value = str(user_id)
        row.secret = False


def _local_now(config: dict) -> datetime:
    return datetime.now(ZoneInfo(config["timezone"]))


def _local_day_utc_bounds(config: dict) -> tuple[datetime, datetime]:
    now = _local_now(config)
    start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def expected_publications_now(config: dict, now: datetime | None = None) -> int:
    local_now = now.astimezone(ZoneInfo(config["timezone"])) if now else _local_now(config)
    start = local_now.replace(hour=config["publish_start_hour"], minute=0, second=0, microsecond=0)
    if config["publish_end_hour"] >= 24:
        end = start.replace(hour=0) + timedelta(days=1)
    else:
        end = local_now.replace(hour=config["publish_end_hour"], minute=0, second=0, microsecond=0)
    if local_now < start:
        return 0
    if local_now >= end:
        return int(config["daily_target"])
    total_seconds = max(1.0, (end - start).total_seconds())
    elapsed = max(0.0, (local_now - start).total_seconds())
    return min(int(config["daily_target"]), max(1, math.floor((elapsed / total_seconds) * int(config["daily_target"])) + 1))


def trend_score(video: dict) -> float:
    views = max(0, int(video.get("view_count") or 0))
    likes = max(0, int(video.get("like_count") or 0))
    comments = max(0, int(video.get("comment_count") or 0))
    published = _parse_iso(video.get("published_at"))
    age_hours = max(1.0, (datetime.now(timezone.utc) - published).total_seconds() / 3600.0) if published else 72.0
    engagement = views + likes * 10 + comments * 18
    freshness = 1.0 + min(2.0, 72.0 / age_hours)
    return float(engagement) * freshness


def _discovery_due(config: dict) -> bool:
    previous = _parse_iso(config.get("last_discovery_at"))
    if previous is None:
        return True
    return (datetime.now(timezone.utc) - previous).total_seconds() >= DISCOVERY_INTERVAL_SECONDS


def _can_queue_source_job(db: Session, user: User, duration_seconds: int, requested_clips: int) -> tuple[bool, str]:
    allowed, reason = can_use_tool(db, user)
    if not allowed:
        return False, reason
    if user.role != "superadmin":
        plan = ensure_plan(db, user.tenant_id)
        allowed, reason = can_create_job(db, plan, duration_seconds, requested_clips)
        if not allowed:
            return False, reason
    if settings.environment.strip().lower() == "production" and not download_access_configured():
        return False, "O download do YouTube ainda não está autenticado no servidor."
    return True, ""


def _queue_source_jobs(db: Session, user: User, config: dict) -> tuple[int, str | None]:
    auto_ids = _auto_job_ids(db, user.id)
    active_jobs = (
        db.query(Job)
        .filter(Job.id.in_(auto_ids), Job.status.in_(["queued", "checking_ffmpeg", "downloading", "extracting_audio", "transcribing", "selecting_clips", "rendering"]))
        .count()
        if auto_ids
        else 0
    )
    clips_available = (
        db.query(Clip)
        .filter(Clip.job_id.in_(auto_ids), Clip.status.notin_(["archived"]))
        .count()
        if auto_ids
        else 0
    )
    desired_buffer = max(int(config["daily_target"]), int(config["clips_per_source"]) * 2)
    potential = clips_available + active_jobs * int(config["clips_per_source"])
    capacity = max(0, int(config["max_active_jobs"]) - active_jobs)
    jobs_needed = min(capacity, max(0, math.ceil((desired_buffer - potential) / int(config["clips_per_source"]))))
    if jobs_needed <= 0:
        return 0, None
    if not _discovery_due(config):
        return 0, None

    try:
        videos = discover_videos(
            keyword=config["keyword"],
            region=config["region"],
            max_results=300,
            days=config["days"],
        )
    except Exception as exc:
        return 0, f"Pesquisa automática do YouTube falhou: {exc}"

    config["last_discovery_at"] = _iso_now()
    used_video_ids = {
        row.youtube_id
        for row in db.query(SourceVideo.youtube_id).filter(SourceVideo.user_id == user.id).all()
    }
    candidates = [
        video
        for video in videos
        if video.get("video_id")
        and video.get("video_id") not in used_video_ids
        and int(video.get("view_count") or 0) >= int(config["min_views"])
        and int(video.get("like_count") or 0) >= int(config["min_likes"])
    ]
    candidates.sort(key=trend_score, reverse=True)
    queued = 0
    last_error: str | None = None

    for video in candidates[: max(jobs_needed * 3, jobs_needed)]:
        if queued >= jobs_needed:
            break
        duration = max(0, int(video.get("duration_seconds") or 0))
        allowed, reason = _can_queue_source_job(db, user, duration, int(config["clips_per_source"]))
        if not allowed:
            last_error = reason
            break

        source = SourceVideo(
            tenant_id=user.tenant_id,
            user_id=user.id,
            youtube_id=str(video["video_id"]),
            title=str(video.get("title") or "Vídeo do YouTube")[:500],
            channel_title=str(video.get("channel_title") or "")[:250],
            original_url=str(video.get("url") or f"https://www.youtube.com/watch?v={video['video_id']}")[:800],
            thumbnail_url=str(video.get("thumbnail_url") or "")[:800],
            duration_seconds=duration,
            rights_confirmed=True,
        )
        db.add(source)
        db.flush()
        job = Job(
            tenant_id=user.tenant_id,
            user_id=user.id,
            source_video_id=source.id,
            requested_clips=int(config["clips_per_source"]),
            status="queued",
            progress=0,
        )
        db.add(job)
        db.flush()
        _mark_auto_job(db, job.id, user.id)
        config["last_selected_video_id"] = source.youtube_id
        config["last_selected_video_title"] = source.title
        queued += 1

    db.commit()
    if queued == 0 and last_error is None:
        last_error = "Nenhum vídeo novo atendeu aos parâmetros automáticos nesta pesquisa."
    return queued, last_error


def _source_path_for_clip(clip: Clip) -> Path | None:
    output = Path(clip.file_path)
    root = output.parent
    for extension in (".mp4", ".mkv", ".webm", ".mov"):
        candidate = root / f"source{extension}"
        if candidate.is_file():
            return candidate
    for candidate in sorted(root.glob("source.*")):
        if candidate.is_file() and candidate.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}:
            return candidate
    return None


def _remove_generated_caption(clip: Clip) -> None:
    if not (clip.subtitle_path or "").strip():
        return
    source = _source_path_for_clip(clip)
    output = Path(clip.file_path)
    if source is None or not output.is_file():
        raise RuntimeError(f"Arquivo original do corte {clip.id} não foi encontrado para remover a legenda.")
    temporary = output.with_name(f"{output.stem}.auto-clean{output.suffix}")
    ensure_ffmpeg()
    try:
        render_vertical_clip(
            source,
            temporary,
            clip.start_seconds,
            clip.end_seconds,
            None,
            caption_position=clip.caption_position,
            caption_margin_v=clip.caption_margin_v,
            caption_font_size=clip.caption_font_size,
        )
        temporary.replace(output)
    except FFmpegError as exc:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"Falha ao remover legenda do corte {clip.id}: {exc}") from exc
    subtitle = Path(clip.subtitle_path)
    subtitle.unlink(missing_ok=True)
    clip.subtitle_path = ""
    clip.updated_at = datetime.now(timezone.utc)


def _clean_ready_clips(db: Session, user_id: int) -> tuple[int, str | None]:
    auto_ids = _auto_job_ids(db, user_id)
    if not auto_ids:
        return 0, None
    clips = (
        db.query(Clip)
        .filter(
            Clip.user_id == user_id,
            Clip.job_id.in_(auto_ids),
            Clip.status.in_(["ready", "approved", "upload_failed"]),
            Clip.subtitle_path != "",
        )
        .order_by(Clip.id.asc())
        .limit(MAX_CLEAN_PER_TICK)
        .all()
    )
    cleaned = 0
    for clip in clips:
        try:
            _remove_generated_caption(clip)
            db.commit()
            cleaned += 1
        except Exception as exc:
            db.rollback()
            return cleaned, str(exc)
    return cleaned, None


def _youtube_started_today(db: Session, user_id: int, auto_ids: list[int], config: dict) -> int:
    if not auto_ids:
        return 0
    start, end = _local_day_utc_bounds(config)
    return (
        db.query(Clip)
        .filter(
            Clip.user_id == user_id,
            Clip.job_id.in_(auto_ids),
            Clip.status.in_(["upload_queued", "uploading", "uploaded"]),
            Clip.updated_at >= start,
            Clip.updated_at < end,
        )
        .count()
    )


def _queue_youtube_due(db: Session, user: User, config: dict) -> tuple[int, str | None]:
    if not config["publish_youtube"]:
        return 0, None
    if not youtube_connection_status(db, user.id).get("connected"):
        return 0, "Conecte o YouTube deste perfil para o modo automático publicar."
    auto_ids = _auto_job_ids(db, user.id)
    expected = expected_publications_now(config)
    already = _youtube_started_today(db, user.id, auto_ids, config)
    due = max(0, expected - already)
    if due <= 0 or not auto_ids:
        return 0, None
    clips = (
        db.query(Clip)
        .filter(
            Clip.user_id == user.id,
            Clip.job_id.in_(auto_ids),
            Clip.status.in_(["ready", "approved", "upload_failed"]),
            Clip.subtitle_path == "",
        )
        .order_by(Clip.id.asc())
        .limit(due)
        .all()
    )
    for clip in clips:
        clip.status = "upload_queued"
        clip.upload_privacy = "public"
        clip.upload_error = None
        clip.updated_at = datetime.now(timezone.utc)
    db.commit()
    return len(clips), None


def _tiktok_post_title(clip: Clip) -> str:
    try:
        tags = json.loads(clip.tags_json or "[]")
        if not isinstance(tags, list):
            tags = []
    except (json.JSONDecodeError, TypeError):
        tags = []
    hashtags = " ".join(f"#{str(tag).strip().lstrip('#')}" for tag in tags[:8] if str(tag).strip())
    base = (clip.copy_text or clip.description or clip.title or "Short").strip()
    return f"{base}\n\n{hashtags}".strip()[:2200]


def _tiktok_started_today(db: Session, user_id: int, auto_ids: list[int], config: dict) -> int:
    if not auto_ids:
        return 0
    start, end = _local_day_utc_bounds(config)
    return (
        db.query(TikTokPost)
        .join(Clip, Clip.id == TikTokPost.clip_id)
        .filter(
            TikTokPost.user_id == user_id,
            Clip.job_id.in_(auto_ids),
            TikTokPost.created_at >= start,
            TikTokPost.created_at < end,
        )
        .count()
    )


def _queue_tiktok_due(db: Session, user: User, config: dict) -> tuple[int, str | None]:
    if not config["publish_tiktok"]:
        return 0, None
    if not config["music_usage_confirmed"]:
        return 0, "A declaração de uso de música do TikTok precisa estar confirmada no Modo Automático."
    if not tiktok_connection_status(db, user.id).get("connected"):
        return 0, "Conecte o TikTok deste perfil para o modo automático publicar."
    try:
        creator = get_creator_info(db, user.id, force=True)
        clear_legacy_unaudited_state(db, user_id=user.id)
        recover_retryable_draft_uploads(db, user_id=user.id)
        creator = apply_unaudited_public_block(db, user_id=user.id, creator=creator)
    except RuntimeError as exc:
        return 0, str(exc)

    privacy = config["tiktok_privacy_level"]
    options = creator.get("privacy_level_options") or []
    if privacy not in options:
        return 0, creator.get("public_posting_block_reason") or "O TikTok não liberou a privacidade configurada para Direct Post nesta conta."

    auto_ids = _auto_job_ids(db, user.id)
    expected = expected_publications_now(config)
    already = _tiktok_started_today(db, user.id, auto_ids, config)
    due = max(0, expected - already)
    if due <= 0 or not auto_ids:
        return 0, None

    existing_clip_ids = {
        row.clip_id
        for row in db.query(TikTokPost).filter(TikTokPost.user_id == user.id).all()
    }
    max_duration = int(creator.get("max_video_post_duration_sec") or 60)
    candidate_rows = (
        db.query(Clip)
        .filter(
            Clip.user_id == user.id,
            Clip.job_id.in_(auto_ids),
            Clip.status != "archived",
            Clip.subtitle_path == "",
        )
        .order_by(Clip.id.asc())
        .all()
    )
    queued = 0
    for clip in candidate_rows:
        if queued >= due:
            break
        if clip.id in existing_clip_ids or not Path(clip.file_path).is_file():
            continue
        if max(0.0, clip.end_seconds - clip.start_seconds) > max_duration:
            continue
        post = TikTokPost(
            user_id=user.id,
            clip_id=clip.id,
            status="queued",
            privacy_level=privacy,
            title=_tiktok_post_title(clip),
            disable_comment=not bool(config["allow_comment"]) or bool(creator.get("comment_disabled")),
            disable_duet=not bool(config["allow_duet"]) or bool(creator.get("duet_disabled")),
            disable_stitch=not bool(config["allow_stitch"]) or bool(creator.get("stitch_disabled")),
            publish_id=None,
            error=None,
        )
        db.add(post)
        existing_clip_ids.add(clip.id)
        queued += 1
    db.commit()
    return queued, None


def automation_status(db: Session, user_id: int, config: dict | None = None) -> dict:
    config = config or load_auto_config(db, user_id)
    auto_ids = _auto_job_ids(db, user_id)
    start, end = _local_day_utc_bounds(config)
    active_jobs = (
        db.query(Job)
        .filter(Job.id.in_(auto_ids), Job.status.in_(["queued", "checking_ffmpeg", "downloading", "extracting_audio", "transcribing", "selecting_clips", "rendering"]))
        .count()
        if auto_ids
        else 0
    )
    clean_ready = (
        db.query(Clip)
        .filter(Clip.job_id.in_(auto_ids), Clip.status.in_(["ready", "approved", "upload_failed"]), Clip.subtitle_path == "")
        .count()
        if auto_ids
        else 0
    )
    waiting_caption_removal = (
        db.query(Clip)
        .filter(Clip.job_id.in_(auto_ids), Clip.status.in_(["ready", "approved", "upload_failed"]), Clip.subtitle_path != "")
        .count()
        if auto_ids
        else 0
    )
    youtube_today = _youtube_started_today(db, user_id, auto_ids, config)
    tiktok_today = _tiktok_started_today(db, user_id, auto_ids, config)
    return {
        "enabled": bool(config["enabled"]),
        "active_jobs": active_jobs,
        "clean_ready": clean_ready,
        "waiting_caption_removal": waiting_caption_removal,
        "youtube_today": youtube_today,
        "tiktok_today": tiktok_today,
        "expected_now": expected_publications_now(config),
        "daily_target": int(config["daily_target"]),
        "last_run_at": config.get("last_run_at"),
        "last_discovery_at": config.get("last_discovery_at"),
        "last_selected_video_id": config.get("last_selected_video_id"),
        "last_selected_video_title": config.get("last_selected_video_title"),
        "last_error": config.get("last_error"),
        "day_start_utc": start.isoformat(),
        "day_end_utc": end.isoformat(),
    }


def run_user_automatic_mode(user_id: int) -> dict:
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        if not user or not user.active:
            return {"ok": False, "reason": "user_inactive"}
        config = load_auto_config(db, user.id)
        if not config["enabled"]:
            return {"ok": True, "enabled": False}
        if not config["rights_confirmed"]:
            config["enabled"] = False
            config["last_error"] = "Modo automático pausado: falta a confirmação de direitos/licença/autorização."
            save_auto_config(db, user.id, config)
            return {"ok": False, "reason": "rights_not_confirmed"}

        warnings: list[str] = []
        queued_jobs, job_warning = _queue_source_jobs(db, user, config)
        if job_warning:
            warnings.append(job_warning)

        cleaned, clean_warning = _clean_ready_clips(db, user.id)
        if clean_warning:
            warnings.append(clean_warning)

        youtube_queued, youtube_warning = _queue_youtube_due(db, user, config)
        if youtube_warning:
            warnings.append(youtube_warning)

        tiktok_queued, tiktok_warning = _queue_tiktok_due(db, user, config)
        if tiktok_warning:
            warnings.append(tiktok_warning)

        config["last_run_at"] = _iso_now()
        config["last_error"] = " | ".join(dict.fromkeys(warnings))[:2000] if warnings else None
        save_auto_config(db, user.id, config)
        return {
            "ok": not warnings,
            "enabled": True,
            "queued_jobs": queued_jobs,
            "captions_removed": cleaned,
            "youtube_queued": youtube_queued,
            "tiktok_queued": tiktok_queued,
            "warnings": warnings,
            "status": automation_status(db, user.id, config),
        }
    finally:
        db.close()


def run_automatic_modes() -> None:
    db = SessionLocal()
    try:
        rows = db.query(SystemSetting).filter(SystemSetting.key.like(f"{AUTO_SETTING_PREFIX}%")).all()
        user_ids: list[int] = []
        for row in rows:
            try:
                user_ids.append(int(row.key.split(":", 1)[1]))
            except (IndexError, ValueError):
                continue
    finally:
        db.close()

    for user_id in user_ids:
        try:
            run_user_automatic_mode(user_id)
        except Exception:
            # Automatic mode is intentionally isolated from the existing worker.
            # A fault here must never interrupt manual processing or uploads.
            continue
