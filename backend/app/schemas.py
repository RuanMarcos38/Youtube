from datetime import datetime
from pydantic import BaseModel, Field, HttpUrl


class TrendingVideo(BaseModel):
    video_id: str
    title: str
    channel_title: str
    thumbnail_url: str
    url: str
    published_at: str | None = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration_seconds: int = 0


class JobCreate(BaseModel):
    video_id: str
    title: str
    channel_title: str = ""
    thumbnail_url: str = ""
    url: HttpUrl | None = None
    requested_clips: int = Field(default=3, ge=1, le=10)
    rights_confirmed: bool


class SourceVideoOut(BaseModel):
    id: int
    youtube_id: str
    title: str
    channel_title: str
    original_url: str
    thumbnail_url: str
    rights_confirmed: bool

    model_config = {"from_attributes": True}


class ClipOut(BaseModel):
    id: int
    job_id: int
    start_seconds: float
    end_seconds: float
    hook: str
    reason: str
    title: str
    description: str
    copy: str
    tags: list[str]
    media_url: str
    status: str
    youtube_video_id: str | None = None
    upload_error: str | None = None
    created_at: datetime


class JobOut(BaseModel):
    id: int
    status: str
    progress: int
    error: str | None
    requested_clips: int
    created_at: datetime
    updated_at: datetime
    source_video: SourceVideoOut
    clips: list[ClipOut]


class UploadRequest(BaseModel):
    privacy_status: str = Field(default="private", pattern="^(private|unlisted|public)$")


class OAuthStartResponse(BaseModel):
    authorization_url: str


class OAuthStatusResponse(BaseModel):
    configured: bool
    connected: bool
    channel_id: str | None = None
    channel_title: str | None = None
    redirect_uri: str
