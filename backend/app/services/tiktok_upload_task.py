from pathlib import Path

from ..database import SessionLocal
from ..models import Clip, TikTokPost
from .tiktok_upload import TikTokPostLimitError, direct_post_video, fetch_post_status


FAIL_REASON_MESSAGES = {
    "file_format_check_failed": "O TikTok recusou o formato do arquivo do vídeo.",
    "duration_check_failed": "O TikTok recusou a duração do vídeo.",
    "frame_rate_check_failed": "O TikTok recusou a taxa de quadros do vídeo.",
    "picture_size_check_failed": "O TikTok recusou as dimensões/resolução do vídeo.",
    "spam_risk_too_many_posts": "O TikTok bloqueou temporariamente novas publicações por excesso de posts nas últimas 24 horas.",
    "reached_active_user_cap": "O aplicativo TikTok atingiu o limite atual de usuários/publicações permitido.",
    "internal": "O TikTok informou uma falha interna durante a publicação. Tente novamente mais tarde.",
}


def _pause_user_queue(db, user_id: int, message: str, current_post_id: int) -> None:
    current = db.get(TikTokPost, current_post_id)
    if current:
        current.status = "paused_limit"
        current.error = message
    for queued in db.query(TikTokPost).filter(TikTokPost.user_id == user_id, TikTokPost.status == "queued").all():
        queued.status = "paused_limit"
        queued.error = message
    db.commit()


def _failed_message(reason: str) -> str:
    reason = (reason or "unknown").strip()
    return FAIL_REASON_MESSAGES.get(reason, f"O TikTok não concluiu a publicação ({reason}).")


def run_tiktok_upload(post_id: int) -> None:
    db = SessionLocal()
    try:
        post = db.get(TikTokPost, post_id)
        if not post:
            return
        clip = db.query(Clip).filter(Clip.id == post.clip_id, Clip.user_id == post.user_id).first()
        if not clip:
            post.status = "failed"
            post.error = "Corte não encontrado para publicar no TikTok."
            db.commit()
            return

        post.status = "uploading"
        post.error = None
        db.commit()
        publish_id = direct_post_video(
            db,
            user_id=post.user_id,
            file_path=Path(clip.file_path),
            title=post.title,
            privacy_level=post.privacy_level,
            disable_comment=post.disable_comment,
            disable_duet=post.disable_duet,
            disable_stitch=post.disable_stitch,
        )
        # FILE_UPLOAD only means TikTok received the bytes. Keep the video on the
        # TikTok tab until the official status endpoint returns PUBLISH_COMPLETE.
        post.status = "processing"
        post.publish_id = publish_id
        post.error = "TikTok recebeu o arquivo e está processando/moderando a publicação."
        db.commit()
    except TikTokPostLimitError as exc:
        db.rollback()
        post = db.get(TikTokPost, post_id)
        if post:
            _pause_user_queue(db, post.user_id, str(exc), post_id)
    except Exception as exc:
        db.rollback()
        post = db.get(TikTokPost, post_id)
        if post:
            post.status = "failed"
            post.error = str(exc)
            db.commit()
    finally:
        db.close()


def refresh_tiktok_post(post_id: int) -> None:
    """Reconcile a local TikTok queue item with TikTok's authoritative status."""
    db = SessionLocal()
    try:
        post = db.get(TikTokPost, post_id)
        if not post or not post.publish_id or post.status not in {"processing", "submitted"}:
            return
        result = fetch_post_status(db, user_id=post.user_id, publish_id=post.publish_id)
        remote = result["status"]
        if remote == "PUBLISH_COMPLETE":
            post.status = "published"
            post.error = None
        elif remote == "FAILED":
            reason = result.get("fail_reason") or "unknown"
            message = _failed_message(reason)
            if reason in {"spam_risk_too_many_posts", "reached_active_user_cap"}:
                _pause_user_queue(db, post.user_id, message, post.id)
                return
            post.status = "failed"
            post.error = message
        elif remote in {"PROCESSING_UPLOAD", "PROCESSING_DOWNLOAD", "SEND_TO_USER_INBOX"}:
            post.status = "processing"
            post.error = "TikTok ainda está processando/moderando esta publicação."
        else:
            post.status = "processing"
            post.error = f"Aguardando confirmação do TikTok ({remote or 'status pendente'})."
        db.commit()
    except TikTokPostLimitError as exc:
        db.rollback()
        post = db.get(TikTokPost, post_id)
        if post:
            _pause_user_queue(db, post.user_id, str(exc), post.id)
    except Exception as exc:
        db.rollback()
        post = db.get(TikTokPost, post_id)
        if post and post.status in {"processing", "submitted"}:
            # A temporary status-check failure must never turn a potentially
            # successful TikTok post into a failed one. Keep it visible and retry.
            post.error = f"Aguardando confirmação do TikTok: {exc}"
            db.commit()
    finally:
        db.close()
