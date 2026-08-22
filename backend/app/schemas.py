from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, HttpUrl


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


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    company_name: str | None = Field(default=None, max_length=180)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class ActivationRequest(BaseModel):
    email: EmailStr
    order_code: str = Field(min_length=4, max_length=160)
    password: str = Field(min_length=8, max_length=200)


class TeamUserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    role: str = Field(default="member", pattern="^(admin|member)$")


class UserOut(BaseModel):
    id: int
    tenant_id: int
    email: str
    display_name: str
    role: str
    active: bool
    billing_status: str
    checkout_url: str
    upgrade_url: str
    plan_code: str
    monthly_job_limit: int
    unlimited: bool
    jobs_used: int
    jobs_remaining: int | None = None


class TeamUserOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    active: bool
    youtube_connected: bool = False
    youtube_channel_title: str | None = None


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
