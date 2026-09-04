import json
from googleapiclient.errors import HttpError


class YouTubeQuotaError(RuntimeError):
    pass


class YouTubeUploadLimitError(YouTubeQuotaError):
    """The channel reached YouTube's own rolling 24-hour upload cap."""


class YouTubeAuthError(RuntimeError):
    pass


def google_error_reason(exc: HttpError) -> tuple[str, str]:
    reason = "unknown"
    message = str(exc)
    try:
        payload = json.loads(exc.content.decode("utf-8"))
        error = payload.get("error", {})
        message = error.get("message", message)
        errors = error.get("errors", [])
        if errors:
            reason = errors[0].get("reason", reason)
    except Exception:
        pass
    return reason, message


def raise_for_youtube_error(exc: HttpError) -> None:
    reason, message = google_error_reason(exc)
    if reason == "uploadLimitExceeded":
        raise YouTubeUploadLimitError(
            "O limite diário de uploads deste canal foi atingido. Os envios restantes foram pausados para evitar novas falhas; tente novamente após a janela de 24 horas."
        ) from exc
    if reason in {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}:
        raise YouTubeQuotaError(f"YouTube quota/rate limit: {message}") from exc
    if exc.resp.status in {401, 403}:
        raise YouTubeAuthError(f"YouTube authorization failed: {message}") from exc
    raise RuntimeError(f"YouTube API error ({reason}): {message}") from exc
