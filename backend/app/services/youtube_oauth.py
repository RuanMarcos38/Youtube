import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import User, YouTubeConnection

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def _env_client_config() -> dict | None:
    if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
        return None
    return {
        "web": {
            "client_id": settings.google_oauth_client_id,
            "project_id": settings.google_oauth_project_id or "shortsflow-ai",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": settings.google_oauth_client_secret,
            "redirect_uris": [settings.youtube_oauth_redirect_uri],
        }
    }


def oauth_configured() -> bool:
    return bool(_env_client_config()) or settings.oauth_secrets_path.exists()


def _new_flow(state: str | None = None, code_verifier: str | None = None) -> Flow:
    config = _env_client_config()
    kwargs = {"scopes": SCOPES, "redirect_uri": settings.youtube_oauth_redirect_uri}
    if state:
        kwargs["state"] = state
    if code_verifier:
        kwargs["code_verifier"] = code_verifier
    if config:
        return Flow.from_client_config(config, **kwargs)
    if settings.oauth_secrets_path.exists():
        return Flow.from_client_secrets_file(str(settings.oauth_secrets_path), **kwargs)
    raise RuntimeError("Google OAuth não está configurado no servidor.")


def _connection(db: Session, user_id: int) -> YouTubeConnection:
    connection = db.query(YouTubeConnection).filter(YouTubeConnection.user_id == user_id).first()
    if connection is None:
        connection = YouTubeConnection(user_id=user_id)
        db.add(connection)
        db.flush()
    return connection


def build_authorization_url(db: Session, user: User) -> str:
    flow = _new_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        # Always show Google's account picker before consent. This is required
        # for the multi-tenant SaaS flow so each ShortsFlow profile can choose
        # the exact Google/YouTube account that owns the channel it wants to use,
        # instead of silently reusing the account already active in the browser.
        prompt="select_account consent",
    )
    connection = _connection(db, user.id)
    connection.oauth_state = state
    connection.code_verifier = flow.code_verifier
    db.commit()
    return authorization_url


def _channel_metadata(creds: Credentials) -> tuple[str | None, str | None]:
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    response = youtube.channels().list(part="snippet", mine=True, maxResults=1).execute()
    items = response.get("items", [])
    if not items:
        return None, None
    item = items[0]
    return item.get("id"), item.get("snippet", {}).get("title")


def complete_oauth(db: Session, code: str, state: str) -> int:
    connection = db.query(YouTubeConnection).filter(YouTubeConnection.oauth_state == state).first()
    if not connection:
        raise RuntimeError("Estado OAuth inválido. Inicie a conexão do YouTube novamente.")

    flow = _new_flow(state=state, code_verifier=connection.code_verifier)
    flow.fetch_token(code=code)
    creds = flow.credentials
    channel_id, channel_title = _channel_metadata(creds)

    connection.token_json = creds.to_json()
    connection.channel_id = channel_id
    connection.channel_title = channel_title
    connection.oauth_state = None
    connection.code_verifier = None
    db.commit()
    return connection.user_id


def _credentials_from_connection(connection: YouTubeConnection, db: Session) -> Credentials:
    if not connection.token_json:
        raise RuntimeError("YouTube não está conectado para este perfil.")
    info = json.loads(connection.token_json)
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        connection.token_json = creds.to_json()
        db.commit()
    if not creds.valid:
        raise RuntimeError("As credenciais do YouTube deste perfil são inválidas. Reconecte o canal.")
    return creds


def get_credentials(user_id: int) -> Credentials:
    db = SessionLocal()
    try:
        connection = db.query(YouTubeConnection).filter(YouTubeConnection.user_id == user_id).first()
        if not connection:
            raise RuntimeError("YouTube não está conectado para este perfil.")
        return _credentials_from_connection(connection, db)
    finally:
        db.close()


def get_connection_status(db: Session, user_id: int) -> dict:
    configured = oauth_configured()
    connection = db.query(YouTubeConnection).filter(YouTubeConnection.user_id == user_id).first()
    connected = False
    if configured and connection and connection.token_json:
        try:
            _credentials_from_connection(connection, db)
            connected = True
        except Exception:
            connected = False
    return {
        "configured": configured,
        "connected": connected,
        "channel_id": connection.channel_id if connected and connection else None,
        "channel_title": connection.channel_title if connected and connection else None,
        "redirect_uri": settings.youtube_oauth_redirect_uri,
    }


def is_connected(user_id: int) -> bool:
    db = SessionLocal()
    try:
        return bool(get_connection_status(db, user_id)["connected"])
    finally:
        db.close()


def disconnect(db: Session, user_id: int) -> None:
    connection = db.query(YouTubeConnection).filter(YouTubeConnection.user_id == user_id).first()
    if connection:
        db.delete(connection)
        db.commit()
