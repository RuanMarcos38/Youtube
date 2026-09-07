from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Clip, SystemSetting, TikTokPost, User
from . import automatic_mode as auto
from .ffmpeg_service import FFmpegError, ensure_ffmpeg, render_vertical_clip
from .tiktok_oauth import get_connection_status as tiktok_connection_status, get_creator_info
from .tiktok_policy import apply_unaudited_public_block, clear_legacy_unaudited_state, recover_retryable_draft_uploads
from .youtube_oauth import get_connection_status as youtube_connection_status


AUTO_CLEAN_PREFIX = "auto_clean:"
MAX_FORCE_CLEAN_PER_TICK = 15
CLEANABLE_STATUSES = ["ready", "approved", "upload_failed", "upload_queued", "uploaded"]
READY_STATUSES = ["ready", "approved", "upload_failed"]


def load_auto_config(db: Session, user_id: int) -> dict:
    return auto.load_auto_config(db, user_id)


def save_auto_config(db: Session, user_id: int, payload: dict) -> dict:
    return auto.save_auto_config(db, user_id, payload)


def _clean_marker_key(clip_id: int) -> str:
    return f"{AUTO_CLEAN_PREFIX}{clip_id}"


def _verified_clip_ids(db: Session, user_id: int) -> set[int]:
    rows = (
        db.query(SystemSetting)
        .filter(SystemSetting.key.like(f"{AUTO_CLEAN_PREFIX}%"), SystemSetting.value == str(user_id))
        .all()
    )
    ids: set[int] = set()
    for row in rows:
        try:
            ids.add(int(row.key.split(":", 1)[1]))
        except (IndexError, ValueError):
            continue
    return ids


def _mark_clip_clean(db: Session, clip: Clip) -> None:
    key = _clean_marker_key(clip.id)
    row = db.get(SystemSetting, key)
    if row is None:
        db.add(SystemSetting(key=key, value=str(clip.user_id), secret=False))
    else:
        row.value = str(clip.user_id)
        row.secret = False


def auto_clip_publish_verified(db: Session, clip: Clip) -> bool:
    """Allow manual clips normally, but hard-block unverified automatic clips."""
    job_marker = db.get(SystemSetting, f"{auto.AUTO_JOB_PREFIX}{clip.job_id}")
    if job_marker is None or str(job_marker.value) != str(clip.user_id):
        return True
    clean_marker = db.get(SystemSetting, _clean_marker_key(clip.id))
    return bool(
        clean_marker
        and str(clean_marker.value) == str(clip.user_id)
        and not (clip.subtitle_path or "").strip()
        and Path(clip.file_path).is_file()
    )


def auto_tiktok_post_publish_verified(db: Session, post: TikTokPost) -> bool:
    clip = db.query(Clip).filter(Clip.id == post.clip_id, Clip.user_id == post.user_id).first()
    return bool(clip and auto_clip_publish_verified(db, clip))


def _force_render_without_caption(clip: Clip) -> None:
    """Re-render an automatic Short from source with no ShortsFlow caption layer.

    This is intentionally executed even when subtitle_path is already empty.
    An empty database field alone is not accepted as proof that burned-in text
    is absent from the video. The clean derivative must be generated again from
    source.* and only then receives the verification marker.
    """
    source = auto._source_path_for_clip(clip)
    output = Path(clip.file_path)
    if source is None or not output.is_file():
        raise RuntimeError(
            f"Arquivo original do corte {clip.id} não foi encontrado. O vídeo não será publicado enquanto a legenda não puder ser removida."
        )

    temporary = output.with_name(f"{output.stem}.auto-mandatory-clean{output.suffix}")
    temporary.unlink(missing_ok=True)
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
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise RuntimeError("A renderização sem legenda não gerou um arquivo válido.")
        temporary.replace(output)
    except FFmpegError as exc:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            f"Falha obrigatória ao remover a legenda do corte {clip.id}: {exc}. O vídeo foi bloqueado para publicação."
        ) from exc
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    subtitle_value = (clip.subtitle_path or "").strip()
    if subtitle_value:
        Path(subtitle_value).unlink(missing_ok=True)
    clip.subtitle_path = ""
    clip.updated_at = datetime.now(timezone.utc)


def _clean_ready_clips_required(db: Session, user_id: int) -> tuple[int, str | None]:
    auto_ids = auto._auto_job_ids(db, user_id)
    if not auto_ids:
        return 0, None
    verified = _verified_clip_ids(db, user_id)
    query = db.query(Clip).filter(
        Clip.user_id == user_id,
        Clip.job_id.in_(auto_ids),
        Clip.status.in_(CLEANABLE_STATUSES),
    )
    if verified:
        query = query.filter(Clip.id.notin_(verified))
    clips = query.order_by(Clip.id.asc()).limit(MAX_FORCE_CLEAN_PER_TICK).all()

    cleaned = 0
    for clip in clips:
        try:
            _force_render_without_caption(clip)
            _mark_clip_clean(db, clip)
            db.commit()
            cleaned += 1
        except Exception as exc:
            db.rollback()
            return cleaned, str(exc)
    return cleaned, None


def _queue_youtube_due_verified(db: Session, user: User, config: dict) -> tuple[int, str | None]:
    if not config["publish_youtube"]:
        return 0, None
    if not youtube_connection_status(db, user.id).get("connected"):
        return 0, "Conecte o YouTube deste perfil para o modo automático publicar."

    auto_ids = auto._auto_job_ids(db, user.id)
    expected = auto.expected_publications_now(config)
    already = auto._youtube_started_today(db, user.id, auto_ids, config)
    due = max(0, expected - already)
    if due <= 0 or not auto_ids:
        return 0, None

    verified = _verified_clip_ids(db, user.id)
    if not verified:
        return 0, None
    clips = (
        db.query(Clip)
        .filter(
            Clip.user_id == user.id,
            Clip.job_id.in_(auto_ids),
            Clip.id.in_(verified),
            Clip.status.in_(READY_STATUSES),
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


def _queue_tiktok_due_verified(db: Session, user: User, config: dict) -> tuple[int, str | None]:
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

    auto_ids = auto._auto_job_ids(db, user.id)
    expected = auto.expected_publications_now(config)
    already = auto._tiktok_started_today(db, user.id, auto_ids, config)
    due = max(0, expected - already)
    if due <= 0 or not auto_ids:
        return 0, None

    verified = _verified_clip_ids(db, user.id)
    if not verified:
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
            Clip.id.in_(verified),
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
    status = auto.automation_status(db, user_id, config)
    auto_ids = auto._auto_job_ids(db, user_id)
    if not auto_ids:
        status["clean_ready"] = 0
        status["waiting_caption_removal"] = 0
        status["caption_removal_required"] = True
        return status

    verified = _verified_clip_ids(db, user_id)
    eligible_ids = {
        row.id
        for row in db.query(Clip.id).filter(
            Clip.user_id == user_id,
            Clip.job_id.in_(auto_ids),
            Clip.status.in_(READY_STATUSES),
        ).all()
    }
    status["clean_ready"] = len(eligible_ids & verified)
    status["waiting_caption_removal"] = len(eligible_ids - verified)
    status["caption_removal_required"] = True
    return status


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
        queued_jobs, job_warning = auto._queue_source_jobs(db, user, config)
        if job_warning:
            warnings.append(job_warning)

        cleaned, clean_warning = _clean_ready_clips_required(db, user.id)
        if clean_warning:
            warnings.append(clean_warning)
            youtube_queued = 0
            tiktok_queued = 0
        else:
            youtube_queued, youtube_warning = _queue_youtube_due_verified(db, user, config)
            if youtube_warning:
                warnings.append(youtube_warning)

            tiktok_queued, tiktok_warning = _queue_tiktok_due_verified(db, user, config)
            if tiktok_warning:
                warnings.append(tiktok_warning)

        config["last_run_at"] = auto._iso_now()
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
        rows = db.query(SystemSetting).filter(SystemSetting.key.like(f"{auto.AUTO_SETTING_PREFIX}%")).all()
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
            # A proteção fica isolada: falhas na automação não derrubam o fluxo manual.
            continue
