import random
import time
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from ..errors import YouTubeAuthError, google_error_reason, raise_for_youtube_error
from .seo_service import YOUTUBE_TAG_COUNT_MAX, YOUTUBE_TAG_TOTAL_MAX, youtube_tag_budget
from .youtube_oauth import get_credentials

RETRIABLE_STATUS_CODES = {500, 502, 503, 504}


def _safe_upload_tags(tags: list[str]) -> list[str]:
    safe: list[str] = []
    seen: set[str] = set()
    for raw in tags or []:
        tag = " ".join(str(raw or "").lstrip("#").split()).strip(" ,.;:|/")
        if not tag:
            continue
        tag = tag[:70].rstrip()
        key = tag.casefold()
        if key in seen:
            continue
        proposed = [*safe, tag]
        if youtube_tag_budget(proposed) > YOUTUBE_TAG_TOTAL_MAX:
            continue
        seen.add(key)
        safe.append(tag)
        if len(safe) >= YOUTUBE_TAG_COUNT_MAX:
            break
    return safe


def upload_video(
    file_path: Path,
    title: str,
    description: str,
    tags: list[str],
    user_id: int,
    privacy_status: str = "public",
    max_retries: int = 5,
) -> str:
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    # ShortsFlow is public-only on YouTube. Ignore legacy caller values so an
    # old frontend or queued record can never turn a new upload private.
    privacy_status = "public"
    youtube = build("youtube", "v3", credentials=get_credentials(user_id), cache_discovery=False)
    body = {
        "snippet": {
            "title": title[:100],
            "description": description,
            "tags": _safe_upload_tags(tags),
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(file_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    retries = 0
    while response is None:
        try:
            _, response = request.next_chunk()
        except HttpError as exc:
            if exc.resp.status in RETRIABLE_STATUS_CODES and retries < max_retries:
                retries += 1
                time.sleep(min(2 ** retries + random.random(), 30))
                continue
            raise_for_youtube_error(exc)
            raise
        except (OSError, TimeoutError, ConnectionError) as exc:
            if retries >= max_retries:
                raise RuntimeError(f"Upload failed after retries: {exc}") from exc
            retries += 1
            time.sleep(min(2 ** retries + random.random(), 30))

    video_id = response.get("id") if response else None
    if not video_id:
        raise RuntimeError("YouTube upload completed without returning a video ID")
    return video_id


def delete_video(video_id: str, user_id: int) -> dict:
    """Delete a video owned by the connected YouTube channel.

    The caller must pass the video id already stored on the user's own Clip.
    A video that was already removed directly in YouTube is treated as deleted
    so ShortsFlow can safely reconcile its local publication history.
    """
    normalized_id = str(video_id or "").strip()
    if not normalized_id:
        raise ValueError("Este Short não possui um vídeo do YouTube vinculado.")

    youtube = build("youtube", "v3", credentials=get_credentials(user_id), cache_discovery=False)
    try:
        youtube.videos().delete(id=normalized_id).execute()
        return {"deleted": True, "already_missing": False}
    except HttpError as exc:
        reason, message = google_error_reason(exc)
        if exc.resp.status == 404 or reason == "videoNotFound":
            return {"deleted": True, "already_missing": True}
        normalized_message = message.lower()
        if reason == "insufficientPermissions" or "insufficient authentication scopes" in normalized_message:
            raise YouTubeAuthError(
                "Para excluir vídeos do canal, reconecte o YouTube uma única vez e autorize a permissão de gerenciamento. "
                "As credenciais do projeto não serão alteradas."
            ) from exc
        raise_for_youtube_error(exc)
        raise
