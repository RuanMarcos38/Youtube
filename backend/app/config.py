from pathlib import Path
from pydantic import AliasChoices, Field
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
    openai_text_model: str = Field(default="gpt-5", validation_alias=AliasChoices("OPENAI_MODEL", "OPENAI_TEXT_MODEL"))
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
    ytdlp_cookies_b64: str = ""
    ytdlp_proxy_url: str = ""
    ytdlp_pot_provider_url: str = ""
    ytdlp_node_path: str = "/usr/local/bin/node"
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    worker_poll_seconds: float = 2.0
    worker_concurrency: int = 2

    auth_cookie_name: str = "shortsflow_session"
    auth_session_hours: int = 168

    kiwify_checkout_url: str = "https://pay.kiwify.com.br/tBv68U5"
    kiwify_upgrade_url: str = "https://pay.kiwify.com.br/8n30IZ9"
    kiwify_base_checkout_code: str = "tBv68U5"
    kiwify_upgrade_checkout_code: str = "8n30IZ9"
    kiwify_webhook_token: str = ""
    base_plan_job_limit: int = 10
    billing_require_active: bool = True

    admin_bootstrap_email: str = "admin@r2rmarketingdigital.com.br"
    admin_bootstrap_password_hash: str = "pbkdf2_sha256$260000$TAZfxFCzS7eQkm_UPco2ZQ==$RIjdlZl30n9mIrZYd1Q_5lBK1t9hmoy9Nvls2ji2B04="

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

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
