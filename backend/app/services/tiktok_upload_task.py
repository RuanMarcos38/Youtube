from pathlib import Path

from ..database import SessionLocal
from ..models import Clip, TikTokPost
from .tiktok_oauth import get_creator_info
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
            "O arquivo foi aceito pelo endpoint de Upload do TikTok. Isso ainda não significa que existe um rascunho visível no aplicativo. "
            "O ShortsFlow continuará consultando o publish_id até o TikTok informar o estado final."
        )
    else:
        post.error = "TikTok recebeu o arquivo por Direct Post e está processando/moderando a publicação."
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
                "O Direct Post está bloqueado pela auditoria do TikTok e o envio para Caixa de Entrada também não pôde ser concluído. "
                f"{exc}"
            ),
        )
        return False

    _finish_submission(db, post, publish_id, draft=True)
    return True


def _unaudited_account_requires_upload_fallback(db, post: TikTokPost) -> bool:
    """Return True when TikTok's unaudited rules do not allow Direct Post.

    TikTok currently permits unaudited Direct Post only when the creator account
    itself is private and the selected viewership is SELF_ONLY. Creator Info is
    cached by the OAuth service, so this normally does not add an extra network
    request immediately after queue creation.
    """
    if post.privacy_level != "SELF_ONLY":
        return True
    try:
        creator = get_creator_info(db, post.user_id)
    except Exception:
        # When the account state cannot be confirmed, keep the conservative
        # official Upload route instead of sending a Direct Post that TikTok is
        # known to reject for public accounts while the client is unaudited.
        return True
    options = {str(value).strip() for value in (creator.get("privacy_level_options") or []) if str(value).strip()}
    account_is_private = "FOLLOWER_OF_CREATOR" in options and "PUBLIC_TO_EVERYONE" not in options
    return not account_is_private


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

        # A previous public-account failure proves that this client is still
        # unaudited. Do not blindly route SELF_ONLY to the inbox: if Creator
        # Info now shows that the TikTok account itself is private, Direct Post
        # is the correct test path and produces a real private post.
        if unaudited_public_block_active(db, user_id=post.user_id) and _unaudited_account_requires_upload_fallback(db, post):
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
            # TikTok remains authoritative. Remember the restriction and use
            # the Upload endpoint only as a fallback for this attempt.
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
            # This is what TikTok's API reports for the Upload flow. It means
            # TikTok says it sent an inbox notification; it does not let the
            # ShortsFlow independently prove that the notification is visible
            # on the creator's phone.
            post.status = "draft_sent"
            post.error = (
                "TikTok confirmou SEND_TO_USER_INBOX: o video foi enviado para a Caixa de Entrada/Rascunhos. "
                "Abra a notificacao no app TikTok e conclua a postagem por la. "
                "O ShortsFlow so removera este corte quando o TikTok retornar PUBLISH_COMPLETE."
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
            post.error = "TikTok ainda está processando este envio."
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
