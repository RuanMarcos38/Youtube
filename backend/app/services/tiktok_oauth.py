import json
import secrets
import time
from threading import Lock
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import TikTokConnection, User

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
BASE_SCOPES = "user.info.basic,video.publish,video.upload"
METRICS_SCOPES = "user.info.basic,user.info.stats,video.list,video.publish,video.upload"
_LOCAL_REDIRECT_URI = "http://localhost:8000/api/tiktok/oauth/callback"
_CREATOR_CACHE_TTL_SECONDS = 45
_CREATOR_CACHE: dict[int, tuple[float, dict]] = {}
_CREATOR_CACHE_LOCK = Lock()


def oauth_configured() -> bool:
    return bool(settings.tiktok_client_key.strip() and settings.tiktok_client_secret.strip())


def oauth_redirect_uri() -> str:
    configured = settings.tiktok_oauth_redirect_uri.strip()
    frontend = settings.frontend_url.strip().rstrip("/")
    if configured and configured != _LOCAL_REDIRECT_URI:
        return configured
    if frontend.startswith("https://"):
        return f"{frontend}/api/tiktok/oauth/callback"
    return configured or _LOCAL_REDIRECT_URI


def _connection(db: Session, user_id: int) -> TikTokConnection:
    connection = db.query(TikTokConnection).filter(TikTokConnection.user_id == user_id).first()
    if connection is None:
        connection = TikTokConnection(user_id=user_id)
        db.add(connection)
        db.flush()
    return connection


def _release_read_transaction(db: Session) -> None:
    """Return a read-only SQL connection to the pool before external I/O."""
    try:
        db.rollback()
    except Exception:
        pass


def clear_creator_info_cache(user_id: int) -> None:
    with _CREATOR_CACHE_LOCK:
        _CREATOR_CACHE.pop(int(user_id), None)


def _cached_creator_info(user_id: int) -> dict | None:
    now = time.monotonic()
    with _CREATOR_CACHE_LOCK:
        cached = _CREATOR_CACHE.get(int(user_id))
        if not cached:
            return None
        expires_at, value = cached
        if expires_at <= now:
            _CREATOR_CACHE.pop(int(user_id), None)
            return None
        return dict(value)


def _store_creator_info(user_id: int, value: dict) -> None:
    with _CREATOR_CACHE_LOCK:
        _CREATOR_CACHE[int(user_id)] = (time.monotonic() + _CREATOR_CACHE_TTL_SECONDS, dict(value))


def _json_response(response: httpx.Response, context: str) -> dict:
    try:
        payload = response.json()
    except ValueError as exc:
        status_code = int(response.status_code or 0)
        if status_code >= 500:
            raise RuntimeError(
                f"TikTok está temporariamente indisponível ao {context} (HTTP {status_code}). Aguarde alguns segundos e tente novamente."
            ) from exc
        raise RuntimeError(
            f"TikTok retornou uma resposta inválida ao {context} (HTTP {status_code or 'desconhecido'})."
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"TikTok retornou uma resposta inesperada ao {context}.")
    return payload


def build_authorization_url(db: Session, user: User, *, include_metrics: bool = False) -> str:
    if not oauth_configured():
        raise RuntimeError(
            "TikTok ainda não está configurado no servidor. Cadastre TIKTOK_CLIENT_KEY e TIKTOK_CLIENT_SECRET do app aprovado no TikTok for Developers."
        )
    state = secrets.token_urlsafe(32)
    connection = _connection(db, user.id)
    connection.oauth_state = state
    db.commit()
    query = urlencode(
        {
            "client_key": settings.tiktok_client_key,
            "response_type": "code",
            "scope": METRICS_SCOPES if include_metrics else BASE_SCOPES,
            "redirect_uri": oauth_redirect_uri(),
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def _token_request(data: dict[str, str]) -> dict:
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    except httpx.RequestError as exc:
        raise RuntimeError("Não foi possível comunicar com o TikTok para concluir a autenticação. Tente novamente.") from exc
    payload = _json_response(response, "concluir a autenticação")
    if response.is_error or not payload.get("access_token"):
        detail = payload.get("error_description") or payload.get("message") or payload.get("error") or response.text
        raise RuntimeError(f"TikTok OAuth não foi concluído: {detail}")
    return payload


def _stamp_token(payload: dict, previous: dict | None = None) -> dict:
    merged = dict(previous or {})
    merged.update(payload)
    expires_in = int(merged.get("expires_in") or 86400)
    merged["_expires_at"] = time.time() + max(60, expires_in - 120)
    return merged


def _profile(access_token: str) -> dict:
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.get(
                USER_INFO_URL,
                params={"fields": "open_id,display_name,avatar_url"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
        payload = _json_response(response, "consultar o perfil")
    except (RuntimeError, httpx.RequestError):
        return {}
    error = payload.get("error") or {}
    if response.is_error or error.get("code") not in {None, "ok", 0}:
        return {}
    return (payload.get("data") or {}).get("user") or {}


def complete_oauth(db: Session, code: str, state: str) -> int:
    if not oauth_configured():
        raise RuntimeError("TikTok OAuth não está configurado.")
    connection = db.query(TikTokConnection).filter(TikTokConnection.oauth_state == state).first()
    if not connection:
        raise RuntimeError("Estado OAuth do TikTok inválido. Inicie a conexão novamente.")

    connection_id = int(connection.id)
    user_id = int(connection.user_id)
    _release_read_transaction(db)

    payload = _token_request(
        {
            "client_key": settings.tiktok_client_key,
            "client_secret": settings.tiktok_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": oauth_redirect_uri(),
        }
    )
    stamped = _stamp_token(payload)
    profile = _profile(str(stamped.get("access_token") or ""))

    connection = (
        db.query(TikTokConnection)
        .filter(TikTokConnection.id == connection_id, TikTokConnection.oauth_state == state)
        .first()
    )
    if not connection:
        _release_read_transaction(db)
        raise RuntimeError("Esta autorização do TikTok já foi concluída ou expirou. Inicie a conexão novamente.")
    connection.token_json = json.dumps(stamped)
    connection.open_id = str(profile.get("open_id") or stamped.get("open_id") or "") or None
    connection.display_name = str(profile.get("display_name") or "") or None
    connection.oauth_state = None
    db.commit()
    clear_creator_info_cache(user_id)
    return user_id


def _refresh(db: Session, connection: TikTokConnection, token: dict) -> dict:
    refresh_token = str(token.get("refresh_token") or "").strip()
    if not refresh_token:
        raise RuntimeError("A conexão do TikTok expirou. Reconecte a conta.")
    connection_id = int(connection.id)
    user_id = int(connection.user_id)
    _release_read_transaction(db)

    payload = _token_request(
        {
            "client_key": settings.tiktok_client_key,
            "client_secret": settings.tiktok_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    )
    stamped = _stamp_token(payload, token)
    connection = db.get(TikTokConnection, connection_id)
    if not connection:
        _release_read_transaction(db)
        raise RuntimeError("A conexão do TikTok não existe mais. Reconecte a conta.")
    connection.token_json = json.dumps(stamped)
    db.commit()
    clear_creator_info_cache(user_id)
    return stamped


def _stored_token(db: Session, user_id: int) -> tuple[TikTokConnection, dict]:
    connection = db.query(TikTokConnection).filter(TikTokConnection.user_id == user_id).first()
    if not connection or not connection.token_json:
        raise RuntimeError("TikTok não está conectado para este perfil.")
    try:
        token = json.loads(connection.token_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Credencial do TikTok inválida. Reconecte a conta.") from exc
    if time.time() >= float(token.get("_expires_at") or 0):
        token = _refresh(db, connection, token)
        connection = db.query(TikTokConnection).filter(TikTokConnection.user_id == user_id).first()
        if not connection:
            raise RuntimeError("A conexão do TikTok não existe mais. Reconecte a conta.")
    return connection, token


def get_access_token(db: Session, user_id: int) -> str:
    if not oauth_configured():
        raise RuntimeError("TikTok ainda não está configurado no servidor.")
    try:
        _, token = _stored_token(db, user_id)
        access_token = str(token.get("access_token") or "").strip()
        if not access_token:
            raise RuntimeError("Credencial do TikTok inválida. Reconecte a conta.")
        return access_token
    finally:
        _release_read_transaction(db)


def token_scopes(db: Session, user_id: int) -> set[str]:
    if not oauth_configured():
        return set()
    try:
        _, token = _stored_token(db, user_id)
        raw = token.get("scope") or token.get("scopes") or ""
        if isinstance(raw, list):
            return {str(item).strip() for item in raw if str(item).strip()}
        return {item.strip() for item in str(raw).replace(" ", ",").split(",") if item.strip()}
    except RuntimeError:
        return set()
    finally:
        _release_read_transaction(db)


def metrics_authorized(db: Session, user_id: int) -> bool:
    scopes = token_scopes(db, user_id)
    return {"user.info.stats", "video.list"}.issubset(scopes)


def get_creator_info(db: Session, user_id: int, *, force: bool = False) -> dict:
    if not force:
        cached = _cached_creator_info(user_id)
        if cached:
            return cached

    access_token = get_access_token(db, user_id)
    scopes = token_scopes(db, user_id)
    if scopes and "video.publish" not in scopes:
        raise RuntimeError(
            "A conta TikTok está conectada, mas não autorizou video.publish. Clique em Trocar conta TikTok e autorize a publicação novamente."
        )

    response: httpx.Response | None = None
    last_network_error: Exception | None = None
    for attempt in range(3):
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(
                    CREATOR_INFO_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json; charset=UTF-8",
                    },
                )
        except httpx.RequestError as exc:
            last_network_error = exc
            if attempt < 2:
                time.sleep(1.0 + attempt)
                continue
            raise RuntimeError(
                "Não foi possível consultar as opções de publicação do TikTok agora. Aguarde alguns segundos e tente novamente."
            ) from exc

        if response.status_code >= 500 and attempt < 2:
            time.sleep(1.0 + attempt)
            continue
        break

    if response is None:
        raise RuntimeError("Não foi possível consultar as opções de publicação do TikTok.") from last_network_error

    payload = _json_response(response, "consultar as opções de publicação")
    error = payload.get("error") or {}
    code = str(error.get("code") or "").strip()
    if response.is_error or code not in {"", "ok", "0"}:
        detail = str(error.get("message") or response.text or "Falha no TikTok").strip()
        if code == "scope_not_authorized":
            raise RuntimeError(
                "O TikTok não autorizou o escopo video.publish nesta conexão. Clique em Trocar conta TikTok e autorize a publicação novamente."
            )
        if code == "access_token_invalid":
            raise RuntimeError("A sessão do TikTok expirou. Clique em Trocar conta TikTok e conecte novamente.")
        if code == "rate_limit_exceeded" or response.status_code == 429:
            raise RuntimeError("O TikTok limitou temporariamente a consulta da conta. Aguarde cerca de 1 minuto e tente novamente.")
        raise RuntimeError(f"TikTok não retornou as opções atuais do criador: {detail}")

    data = payload.get("data") or {}
    privacy_options = [str(item) for item in data.get("privacy_level_options") or [] if str(item).strip()]
    if not privacy_options:
        raise RuntimeError(
            "O TikTok não retornou opções de privacidade para esta conta. Atualize a tela ou reconecte o TikTok antes de publicar."
        )
    try:
        max_duration = max(1, int(data.get("max_video_post_duration_sec") or 60))
    except (TypeError, ValueError):
        max_duration = 60
    result = {
        "creator_username": str(data.get("creator_username") or ""),
        "creator_nickname": str(data.get("creator_nickname") or ""),
        "privacy_level_options": privacy_options,
        "comment_disabled": bool(data.get("comment_disabled", False)),
        "duet_disabled": bool(data.get("duet_disabled", False)),
        "stitch_disabled": bool(data.get("stitch_disabled", False)),
        "max_video_post_duration_sec": max_duration,
    }
    _store_creator_info(user_id, result)
    return result


def get_connection_status(db: Session, user_id: int) -> dict:
    configured = oauth_configured()
    connection = db.query(TikTokConnection).filter(TikTokConnection.user_id == user_id).first()
    has_token = bool(connection and connection.token_json)
    display_name = connection.display_name if connection else None
    _release_read_transaction(db)

    connected = False
    if configured and has_token:
        try:
            get_access_token(db, user_id)
            connected = True
        except Exception:
            connected = False
    scopes = token_scopes(db, user_id) if connected else set()
    return {
        "configured": configured,
        "connected": connected,
        "display_name": display_name if connected else None,
        "redirect_uri": oauth_redirect_uri(),
        "publish_authorized": ("video.publish" in scopes) if scopes else connected,
        "metrics_authorized": {"user.info.stats", "video.list"}.issubset(scopes) if connected else False,
    }


def disconnect(db: Session, user_id: int) -> None:
    connection = db.query(TikTokConnection).filter(TikTokConnection.user_id == user_id).first()
    if connection:
        db.delete(connection)
        db.commit()
    clear_creator_info_cache(user_id)
