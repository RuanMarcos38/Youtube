import json
import secrets
import time
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import TikTokConnection, User

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
SCOPES = "user.info.basic,video.publish"
_LOCAL_REDIRECT_URI = "http://localhost:8000/api/tiktok/oauth/callback"


def oauth_configured() -> bool:
    return bool(settings.tiktok_client_key.strip() and settings.tiktok_client_secret.strip())


def oauth_redirect_uri() -> str:
    """Return the exact callback that must be registered in TikTok.

    Production already serves backend and frontend through the same public HTTPS
    domain. If EasyPanel still inherits the development default callback, derive
    the production callback from FRONTEND_URL instead of sending users back to
    localhost. An explicit TIKTOK_OAUTH_REDIRECT_URI always wins.
    """
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


def build_authorization_url(db: Session, user: User) -> str:
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
            "scope": SCOPES,
            "redirect_uri": oauth_redirect_uri(),
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def _token_request(data: dict[str, str]) -> dict:
    with httpx.Client(timeout=30.0) as client:
        response = client.post(TOKEN_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    payload = response.json()
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
    with httpx.Client(timeout=20.0) as client:
        response = client.get(
            USER_INFO_URL,
            params={"fields": "open_id,display_name,avatar_url"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    payload = response.json()
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
    connection.token_json = json.dumps(stamped)
    connection.open_id = str(profile.get("open_id") or stamped.get("open_id") or "") or None
    connection.display_name = str(profile.get("display_name") or "") or None
    connection.oauth_state = None
    db.commit()
    return connection.user_id


def _refresh(db: Session, connection: TikTokConnection, token: dict) -> dict:
    refresh_token = str(token.get("refresh_token") or "").strip()
    if not refresh_token:
        raise RuntimeError("A conexão do TikTok expirou. Reconecte a conta.")
    payload = _token_request(
        {
            "client_key": settings.tiktok_client_key,
            "client_secret": settings.tiktok_client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    )
    stamped = _stamp_token(payload, token)
    connection.token_json = json.dumps(stamped)
    db.commit()
    return stamped


def get_access_token(db: Session, user_id: int) -> str:
    if not oauth_configured():
        raise RuntimeError("TikTok ainda não está configurado no servidor.")
    connection = db.query(TikTokConnection).filter(TikTokConnection.user_id == user_id).first()
    if not connection or not connection.token_json:
        raise RuntimeError("TikTok não está conectado para este perfil.")
    try:
        token = json.loads(connection.token_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Credencial do TikTok inválida. Reconecte a conta.") from exc
    if time.time() >= float(token.get("_expires_at") or 0):
        token = _refresh(db, connection, token)
    access_token = str(token.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("Credencial do TikTok inválida. Reconecte a conta.")
    return access_token


def get_creator_info(db: Session, user_id: int) -> dict:
    access_token = get_access_token(db, user_id)
    with httpx.Client(timeout=20.0) as client:
        response = client.post(
            CREATOR_INFO_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={},
        )
    payload = response.json()
    error = payload.get("error") or {}
    if response.is_error or error.get("code") not in {None, "ok", 0}:
        detail = error.get("message") or response.text
        raise RuntimeError(f"TikTok não retornou as opções atuais do criador: {detail}")
    data = payload.get("data") or {}
    return {
        "creator_username": str(data.get("creator_username") or ""),
        "creator_nickname": str(data.get("creator_nickname") or ""),
        "privacy_level_options": [str(item) for item in data.get("privacy_level_options") or []],
        "comment_disabled": bool(data.get("comment_disabled", False)),
        "duet_disabled": bool(data.get("duet_disabled", False)),
        "stitch_disabled": bool(data.get("stitch_disabled", False)),
        "max_video_post_duration_sec": int(data.get("max_video_post_duration_sec") or 60),
    }


def get_connection_status(db: Session, user_id: int) -> dict:
    configured = oauth_configured()
    connection = db.query(TikTokConnection).filter(TikTokConnection.user_id == user_id).first()
    connected = False
    if configured and connection and connection.token_json:
        try:
            get_access_token(db, user_id)
            connected = True
        except Exception:
            connected = False
    return {
        "configured": configured,
        "connected": connected,
        "display_name": connection.display_name if connected and connection else None,
        "redirect_uri": oauth_redirect_uri(),
    }


def disconnect(db: Session, user_id: int) -> None:
    connection = db.query(TikTokConnection).filter(TikTokConnection.user_id == user_id).first()
    if connection:
        db.delete(connection)
        db.commit()
