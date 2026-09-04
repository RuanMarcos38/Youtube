import math
from pathlib import Path

import httpx
from sqlalchemy.orm import Session

from .tiktok_oauth import get_access_token

DIRECT_POST_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
MAX_CHUNK_BYTES = 64 * 1024 * 1024


class TikTokUploadError(RuntimeError):
    pass


class TikTokPostLimitError(TikTokUploadError):
    pass


def _chunk_plan(size: int) -> tuple[int, int]:
    if size <= 0:
        raise TikTokUploadError("O arquivo do vídeo está vazio.")
    if size <= MAX_CHUNK_BYTES:
        return size, 1
    count = max(2, math.ceil(size / MAX_CHUNK_BYTES))
    chunk_size = math.ceil(size / count)
    return chunk_size, count


def _raise_tiktok_error(response: httpx.Response, payload: dict) -> None:
    error = payload.get("error") or {}
    code = str(error.get("code") or "unknown")
    message = str(error.get("message") or response.text or "Falha no TikTok")
    if code in {"spam_risk_too_many_posts", "reached_active_user_cap"}:
        raise TikTokPostLimitError(
            "O TikTok atingiu o limite de publicações disponível para esta conta/app nas últimas 24 horas. A fila restante foi pausada."
        )
    raise TikTokUploadError(f"TikTok ({code}): {message}")


def direct_post_video(
    db: Session,
    *,
    user_id: int,
    file_path: Path,
    title: str,
    privacy_level: str,
    disable_comment: bool,
    disable_duet: bool,
    disable_stitch: bool,
) -> str:
    if not file_path.is_file():
        raise TikTokUploadError("Arquivo do corte não encontrado para publicar no TikTok.")

    access_token = get_access_token(db, user_id)
    size = file_path.stat().st_size
    chunk_size, total_chunk_count = _chunk_plan(size)
    body = {
        "post_info": {
            "title": title[:2200],
            "privacy_level": privacy_level,
            "disable_duet": bool(disable_duet),
            "disable_comment": bool(disable_comment),
            "disable_stitch": bool(disable_stitch),
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
        },
        "source_info": {
            "source": "FILE_UPLOAD",
            "video_size": size,
            "chunk_size": chunk_size,
            "total_chunk_count": total_chunk_count,
        },
    }

    with httpx.Client(timeout=60.0) as client:
        init_response = client.post(
            DIRECT_POST_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json=body,
        )
        try:
            payload = init_response.json()
        except ValueError as exc:
            raise TikTokUploadError("TikTok retornou uma resposta inválida ao iniciar a publicação.") from exc
        error = payload.get("error") or {}
        if init_response.is_error or error.get("code") not in {None, "ok", 0}:
            _raise_tiktok_error(init_response, payload)

        data = payload.get("data") or {}
        publish_id = str(data.get("publish_id") or "").strip()
        upload_url = str(data.get("upload_url") or "").strip()
        if not publish_id or not upload_url:
            raise TikTokUploadError("TikTok não retornou os dados necessários para enviar o vídeo.")

        with file_path.open("rb") as source:
            offset = 0
            for index in range(total_chunk_count):
                remaining = size - offset
                current_size = remaining if index == total_chunk_count - 1 else min(chunk_size, remaining)
                chunk = source.read(current_size)
                if len(chunk) != current_size:
                    raise TikTokUploadError("Falha ao ler o arquivo durante o envio ao TikTok.")
                last_byte = offset + current_size - 1
                response = client.put(
                    upload_url,
                    content=chunk,
                    headers={
                        "Content-Type": "video/mp4",
                        "Content-Length": str(current_size),
                        "Content-Range": f"bytes {offset}-{last_byte}/{size}",
                    },
                    timeout=120.0,
                )
                expected = {201} if index == total_chunk_count - 1 else {206, 201}
                if response.status_code not in expected:
                    raise TikTokUploadError(
                        f"TikTok recusou uma parte do arquivo (HTTP {response.status_code})."
                    )
                offset += current_size

    return publish_id
