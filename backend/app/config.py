from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ShortsFlow AI"
    environment: str = "development"
    api_prefix: str = "/api"
    frontend_url: str = "http://localhost:3000"
    cors_origins: str = "http://localhost:3000"

    sqlite_path: str = "data/app.db"
    data_dir: str = "data"

    openai_api_key: str = ""
    openai_text_model: str = "gpt-5"
    openai_transcription_model: str = "whisper-1"
    max_transcript_chars: int = 180000

    youtube_api_key: str = ""
    google_oauth_client_secrets_file: str = "client_secret.json"
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_project_id: str = ""
    youtube_oauth_redirect_uri: str = "http://localhost:8000/api/youtube/oauth/callback"
    youtube_default_region: str = "BR"
    youtube_default_privacy: str = "private"

    ytdlp_cookie_file: str = ""
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    worker_poll_seconds: float = 2.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def backend_dir(self) -> Path:
        return Path(__file__).resolve().parents[1]

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        return path if path.is_absolute() else self.backend_dir / path

    @property
    def sqlite_file(self) -> Path:
        path = Path(self.sqlite_path)
        return path if path.is_absolute() else self.backend_dir / path

    @property
    def oauth_secrets_path(self) -> Path:
        path = Path(self.google_oauth_client_secrets_file)
        return path if path.is_absolute() else self.backend_dir / path

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
settings.data_path.mkdir(parents=True, exist_ok=True)
settings.sqlite_file.parent.mkdir(parents=True, exist_ok=True)
