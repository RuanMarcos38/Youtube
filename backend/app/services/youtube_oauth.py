import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from ..config import settings

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
TOKEN_FILE = settings.data_path / "youtube_token.json"
STATE_FILE = settings.data_path / "youtube_oauth_state.txt"
CHANNEL_FILE = settings.data_path / "youtube_channel.json"


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
    raise RuntimeError(
        "Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET "
        "or provide GOOGLE_OAUTH_CLIENT_SECRETS_FILE."
    )


def _write_oauth_state(state: str, code_verifier: str | None) -> None:
    STATE_FILE.write_text(
        json.dumps({"state": state, "code_verifier": code_verifier}),
        encoding="utf-8",
    )


def _read_oauth_state() -> tuple[str, str | None]:
    if not STATE_FILE.exists():
        return "", None
    raw = STATE_FILE.read_text(encoding="utf-8").strip()
    if not raw:
        return "", None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw, None
    return str(payload.get("state") or ""), payload.get("code_verifier")


def build_authorization_url() -> str:
    flow = _new_flow()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    _write_oauth_state(state, flow.code_verifier)
    return authorization_url


def _write_channel_metadata(creds: Credentials) -> None:
    youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)
    response = youtube.channels().list(part="snippet", mine=True, maxResults=1).execute()
    items = response.get("items", [])
    if not items:
        CHANNEL_FILE.unlink(missing_ok=True)
        return
    item = items[0]
    payload = {
        "channel_id": item.get("id"),
        "channel_title": item.get("snippet", {}).get("title"),
    }
    CHANNEL_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def complete_oauth(code: str, state: str) -> None:
    expected_state, code_verifier = _read_oauth_state()
    if not expected_state or state != expected_state:
        raise RuntimeError("Invalid OAuth state. Start the YouTube connection again.")
    flow = _new_flow(state=state, code_verifier=code_verifier)
    flow.fetch_token(code=code)
    creds = flow.credentials
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    _write_channel_metadata(creds)
    STATE_FILE.unlink(missing_ok=True)


def get_credentials() -> Credentials:
    if not TOKEN_FILE.exists():
        raise RuntimeError("YouTube is not connected. Complete OAuth first.")
    info = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(info, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    if not creds.valid:
        raise RuntimeError("YouTube credentials are invalid. Reconnect the channel.")
    return creds


def get_connection_status() -> dict:
    configured = oauth_configured()
    connected = False
    channel_id = None
    channel_title = None
    if configured:
        try:
            get_credentials()
            connected = True
        except Exception:
            connected = False
    if CHANNEL_FILE.exists():
        try:
            metadata = json.loads(CHANNEL_FILE.read_text(encoding="utf-8"))
            channel_id = metadata.get("channel_id")
            channel_title = metadata.get("channel_title")
        except Exception:
            pass
    return {
        "configured": configured,
        "connected": connected,
        "channel_id": channel_id if connected else None,
        "channel_title": channel_title if connected else None,
        "redirect_uri": settings.youtube_oauth_redirect_uri,
    }


def is_connected() -> bool:
    return bool(get_connection_status()["connected"])


def disconnect() -> None:
    TOKEN_FILE.unlink(missing_ok=True)
    STATE_FILE.unlink(missing_ok=True)
    CHANNEL_FILE.unlink(missing_ok=True)
