import subprocess
from pathlib import Path

from ..config import settings
from ..database import SessionLocal
from ..models import Clip, TikTokPost
from .tiktok_oauth import get_creator_info
from .tiktok_policy import (
    DRAFT_RETRY_MESSAGE,
    DIRECT_POST_UNAVAILABLE_MESSAGE,
    mark_unaudited_public_block,
    release_unaudited_public_queue,
    unaudited_public_block_active,
)
from .tiktok_upload import (
    TikTokPostLimitError,
    TikTokUnauditedClientError,
    direct_post_video,
    fetch_post_status,
)


FAIL_REASON_MESSAGES = {
    "file_format_check_failed": "O TikTok recusou o formato do arquivo do vídeo.",
    "duration_check_failed": "O TikTok recusou a duração do vídeo.",
    "frame_rate_check_failed": "O TikTok recusou a taxa de quadros do vídeo.",
    "picture_size_check_failed": "O TikTok recusou as dimensões/resolução do vídeo.",
    "spam_risk_too_many_posts": "O TikTok bloqueou temporariamente novas publicações por excesso de posts nas últimas 24 horas.",
    "spam_risk_too_many_pending_share": "O TikTok atingiu o limite de rascunhos pendentes enviados pela API. O ShortsFlow manteve os cortes visíveis para nova tentativa; se o erro repetir, aguarde a janela do TikTok ou finalize/descarte notificações pendentes no app.",
    "reached_active_user_cap": "O aplicativo TikTok atingiu o limite atual de usuários/publicações permitido.",
    "internal": "O TikTok informou uma falha interna durante a publicação. Tente novamente mais tarde.",
}


_SOURCE_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov"}


def _source_path_for_clip(clip: Clip) -> Path | None:
    """Locate the downloaded source without changing the stored clip or project."""
    rendered = Path(clip.file_path)
    root = rendered.parent
    for extension in (".mp4", ".mkv", ".webm", ".mov"):
        candidate = root / f"source{extension}"
        if candidate.is_file():
            return candidate
    for candidate in sorted(root.glob("source.*")):
        if candidate.is_file() and candidate.suffix.lower() in _SOURCE_VIDEO_EXTENSIONS:
            return candidate
    return None


def _prepare_tiktok_original_audio_file(clip: Clip) -> Path:
    """Create a temporary TikTok file with the rendered video and source audio only.

    The visual track stays exactly as ShortsFlow rendered it. The audio track is
    replaced from the original downloaded source for the clip time range, so any
    soundtrack/music bed added during editing is never sent to TikTok. The
    persistent Clip file is not overwritten and credentials/settings are not
    touched.
    """
    rendered = Path(clip.file_path)
    if not rendered.is_file():
        raise RuntimeError("Arquivo do corte não encontrado para preparar a publicação no TikTok.")

    source = _source_path_for_clip(clip)
    if source is None:
        raise RuntimeError(
            "Arquivo-fonte original não encontrado. A publicação no TikTok foi interrompida para não enviar música adicionada."
        )

    start = max(0.0, float(clip.start_seconds or 0.0))
    end = max(start, float(clip.end_seconds or start))
    duration = end - start
    if duration <= 0.05:
        raise RuntimeError("O corte não possui duração válida para restaurar o áudio original antes do TikTok.")

    output = rendered.with_name(f"{rendered.stem}.tiktok-original-audio-{clip.id}.mp4")
    output.unlink(missing_ok=True)
    command = [
        settings.ffmpeg_binary,
        "-y",
        "-i",
        str(rendered),
        "-ss",
        f"{start:.3f}",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "48000",
        "-map_metadata",
        "-1",
        "-movflags",
        "+faststart",
        str(output),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        output.unlink(missing_ok=True)
        raise RuntimeError(f"Executável não encontrado: {settings.ffmpeg_binary}") from exc
    except subprocess.CalledProcessError as exc:
        output.unlink(missing_ok=True)
        detail = (exc.stderr or exc.stdout or "Falha ao restaurar o áudio original")[-5000:]
        raise RuntimeError(f"Não foi possível preparar o áudio original para o TikTok: {detail}") from exc

    if not output.is_file() or output.stat().st_size <= 0:
        output.unlink(missing_ok=True)
        raise RuntimeError("O arquivo temporário com áudio original não foi gerado para o TikTok.")
    return output


def _pause_user_queue(db, user_id: int, message: str, current_post_id: int) -> None:
    current = db.get(TikTokPost, current_post_id)
    if current:
        current.status = "paused_limit"
        current.error = message
        current.publish_id = None
    for queued in db.query(TikTokPost).filter(TikTokPost.user_id == user_id, TikTokPost.status == "queued").all():
        queued.status = "paused_limit"
        queued.error = message
        queued.publish_id = None
    db.commit()


def _failed_message(reason: str) -> str:
    reason = (reason or "unknown").strip()
    return FAIL_REASON_MESSAGES.get(reason, f"O TikTok não concluiu a publicação ({reason}).")


def _finish_submission(db, post: TikTokPost, publish_id: str) -> None:
    post.status = "processing"
    post.publish_id = publish_id
    post.error = "TikTok recebeu o arquivo por Direct Post e está processando/moderando a publicação."
    db.commit()


def _unaudited_account_blocks_direct_post(db, post: TikTokPost) -> bool:
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
        # When the account state cannot be confirmed, do not send to drafts as a
        # hidden fallback. Keep the clip visible so the user can retry later.
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
        # unaudited. Only real Direct Post is allowed here; the Upload/inbox
        # endpoint is not used as a fallback because the user requested posts,
        # not drafts.
        if unaudited_public_block_active(db, user_id=post.user_id) and _unaudited_account_blocks_direct_post(db, post):
            release_unaudited_public_queue(
                db,
                user_id=post.user_id,
                current_post_id=post.id,
                current_error=DIRECT_POST_UNAVAILABLE_MESSAGE,
            )
            return

        upload_file: Path | None = None
        try:
            # TikTok receives a temporary derivative whose visual track is the
            # existing rendered Short and whose audio comes only from source.*.
            # This removes any automatically mixed music without touching the
            # original Short used by YouTube, the database row, or credentials.
            upload_file = _prepare_tiktok_original_audio_file(clip)
            publish_id = direct_post_video(
                db,
                user_id=post.user_id,
                file_path=upload_file,
                title=post.title,
                privacy_level=post.privacy_level,
                disable_comment=post.disable_comment,
                disable_duet=post.disable_duet,
                disable_stitch=post.disable_stitch,
            )
        except TikTokUnauditedClientError:
            # TikTok remains authoritative. Remember the restriction and keep
            # the item visible instead of silently converting it to a draft.
            db.rollback()
            post = db.get(TikTokPost, post_id)
            if not post:
                return
            mark_unaudited_public_block(db, user_id=post.user_id)
            release_unaudited_public_queue(db, user_id=post.user_id, current_post_id=post.id)
            return
        finally:
            if upload_file is not None:
                upload_file.unlink(missing_ok=True)

        _finish_submission(db, post, publish_id)
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
            post.status = "ready"
            post.publish_id = None
            post.error = DRAFT_RETRY_MESSAGE
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
