import random
import time
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from ..errors import raise_for_youtube_error
from .youtube_oauth import get_credentials

RETRIABLE_STATUS_CODES = {500, 502, 503, 504}


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
            "tags": tags[:15],
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
