from pathlib import Path

from ..database import SessionLocal
from ..models import Clip, TikTokPost
from .tiktok_policy import (
    mark_unaudited_public_block,
    release_unaudited_public_queue,
    unaudited_public_block_active,
)
from .tiktok_upload import (
    TikTokPostLimitError,
    TikTokUnauditedClientError,
    direct_post_video,
    fetch_post_status,
    upload_video_draft,
)


FAIL_REASON_MESSAGES = {
    "file_format_check_failed": "O TikTok recusou o formato do arquivo do vídeo.",
    "duration_check_failed": "O TikTok recusou a duração do vídeo.",
    "frame_rate_check_failed": "O TikTok recusou a taxa de quadros do vídeo.",
    "picture_size_check_failed": "O TikTok recusou as dimensões/resolução do vídeo.",
    "spam_risk_too_many_posts": "O TikTok bloqueou temporariamente novas publicações por excesso de posts nas últimas 24 horas.",
    "spam_risk_too_many_pending_share": "O TikTok atingiu o limite de rascunhos pendentes. Finalize ou descarte os rascunhos recebidos no app e tente novamente.",
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


def _finish_submission(db, post: TikTokPost, publish_id: str, *, draft: bool) -> None:
    post.status = "processing"
    post.publish_id = publish_id
    if draft:
        post.privacy_level = "DRAFT_INBOX"
        post.error = (
            "TikTok recebeu o vídeo e está preparando o envio para a Caixa de Entrada/Rascunhos. "
            "O ShortsFlow continuará acompanhando este publish_id até a confirmação final."
        )
    else:
        post.error = "TikTok recebeu o arquivo e está processando/moderando a publicação."
    db.commit()


def _fallback_to_draft(db, post: TikTokPost, clip: Clip) -> bool:
    """Try TikTok's official Upload flow after Direct Post is audit-blocked."""
    try:
        publish_id = upload_video_draft(
            db,
            user_id=post.user_id,
            file_path=Path(clip.file_path),
        )
    except TikTokPostLimitError:
        raise
    except Exception as exc:
        release_unaudited_public_queue(
            db,
            user_id=post.user_id,
            current_post_id=post.id,
            current_error=(
                "O Direct Post público está bloqueado pela auditoria do TikTok e o envio para Rascunhos ainda não pôde ser autorizado. "
                f"{exc}"
            ),
        )
        return False

    _finish_submission(db, post, publish_id, draft=True)
    return True


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

        # After TikTok has already proved that this public account cannot use
        # Direct Post while the client is unaudited, do not repeat the same
        # failing request for every queued clip. Use the official Upload flow.
        if unaudited_public_block_active(db, user_id=post.user_id):
            _fallback_to_draft(db, post, clip)
            return

        try:
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
        except TikTokUnauditedClientError:
            # The TikTok response is authoritative. Mark the temporary local
            # gate and immediately fall back to the official inbox/draft flow.
            db.rollback()
            post = db.get(TikTokPost, post_id)
            clip = db.query(Clip).filter(Clip.id == post.clip_id, Clip.user_id == post.user_id).first() if post else None
            if not post or not clip:
                return
            mark_unaudited_public_block(db, user_id=post.user_id)
            _fallback_to_draft(db, post, clip)
            return

        _finish_submission(db, post, publish_id, draft=False)
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
        if not post or not post.publish_id or post.status not in {"processing", "submitted", "draft_sent"}:
            return
        result = fetch_post_status(db, user_id=post.user_id, publish_id=post.publish_id)
        remote = result["status"]
        if remote == "PUBLISH_COMPLETE":
            post.status = "published"
            post.error = None
        elif remote == "SEND_TO_USER_INBOX":
            # TikTok documents this only as delivery to the creator's inbox,
            # not as a completed post. Keep the item visible and keep polling
            # the same publish_id until TikTok later confirms PUBLISH_COMPLETE.
            post.status = "processing"
            post.error = (
                "Rascunho entregue ao TikTok. Abra o aplicativo TikTok, toque na notificação da Caixa de Entrada, "
                "revise o vídeo e conclua a publicação. O vídeo continuará nesta tela até o TikTok confirmar PUBLISH_COMPLETE."
            )
        elif remote == "FAILED":
            reason = result.get("fail_reason") or "unknown"
            message = _failed_message(reason)
            if reason in {"spam_risk_too_many_posts", "spam_risk_too_many_pending_share", "reached_active_user_cap"}:
                _pause_user_queue(db, post.user_id, message, post.id)
                return
            post.status = "failed"
            post.error = message
        elif remote in {"PROCESSING_UPLOAD", "PROCESSING_DOWNLOAD"}:
            post.status = "processing"
            post.error = "TikTok ainda está processando/moderando este envio."
        else:
            post.status = "processing"
            post.error = f"Aguardando confirmação do TikTok ({remote or 'status pendente'})."
        db.commit()
    except TikTokUnauditedClientError as exc:
        db.rollback()
        post = db.get(TikTokPost, post_id)
        if post:
            release_unaudited_public_queue(db, user_id=post.user_id, current_post_id=post.id, current_error=str(exc))
    except TikTokPostLimitError as exc:
        db.rollback()
        post = db.get(TikTokPost, post_id)
        if post:
            _pause_user_queue(db, post.user_id, str(exc), post.id)
    except Exception as exc:
        db.rollback()
        post = db.get(TikTokPost, post_id)
        if post and post.status in {"processing", "submitted", "draft_sent"}:
            post.error = f"Aguardando confirmação do TikTok: {exc}"
            db.commit()
    finally:
        db.close()
