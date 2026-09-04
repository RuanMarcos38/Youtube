from datetime import datetime
from typing import Literal

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
    caption_position: str = "bottom"
    caption_margin_v: int = 120
    caption_font_size: int = 18
    subtitle_srt: str = ""
    status: str
    youtube_video_id: str | None = None
    upload_error: str | None = None
    created_at: datetime
    updated_at: datetime


class ClipCaptionUpdateRequest(BaseModel):
    caption_position: Literal["top", "middle", "bottom"] = "bottom"
    caption_margin_v: int = Field(default=120, ge=40, le=760)
    caption_font_size: int = Field(default=18, ge=14, le=32)
    subtitle_srt: str | None = Field(default=None, max_length=20000)


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
    # Kept compatible with older frontends, but the API always publishes as
    # public. New requests default to public as the only supported mode.
    privacy_status: str = Field(default="public", pattern="^(private|unlisted|public)$")


class OAuthStartResponse(BaseModel):
    authorization_url: str


class OAuthStatusResponse(BaseModel):
    configured: bool
    connected: bool
    channel_id: str | None = None
    channel_title: str | None = None
    redirect_uri: str


class YouTubeVideoMetric(BaseModel):
    video_id: str
    title: str
    thumbnail_url: str = ""
    url: str
    published_at: str | None = None
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    duration_seconds: int = 0


class YouTubeDashboardAlert(BaseModel):
    kind: str
    title: str
    detail: str


class YouTubeMonetizationStatus(BaseModel):
    subscriber_target_early: int
    subscriber_target_full: int
    watch_hours_target_early: int
    watch_hours_target_full: int
    shorts_views_target_early: int
    shorts_views_target_full: int
    uploads_target_early: int
    recent_public_uploads_90d: int
    shorts_views_90d_estimate: int
    watch_hours_last_365d: float | None = None
    subscriber_progress_full: float
    watch_hours_progress_full: float
    shorts_views_progress_full: float
    eligible_early_estimate: bool
    eligible_full_estimate: bool
    near_monetization: bool


class YouTubeLiveAudience(BaseModel):
    concurrent_viewers: int = 0
    active_live_broadcasts: int = 0
    available: bool = True
    refreshed_at: datetime


class YouTubeLiveMetrics(BaseModel):
    channel_id: str | None = None
    channel_title: str | None = None
    channel_thumbnail_url: str = ""
    channel_custom_url: str | None = None
    published_at: str | None = None
    subscriber_count: int = 0
    hidden_subscriber_count: bool = False
    view_count: int = 0
    video_count: int = 0
    recent_videos: list[YouTubeVideoMetric]
    top_video: YouTubeVideoMetric | None = None
    alerts: list[YouTubeDashboardAlert]
    monetization: YouTubeMonetizationStatus
    analytics_available: bool = False
    analytics_note: str | None = None
    views_last_28d: int | None = None
    views_last_90d: int | None = None
    watch_hours_last_365d: float | None = None
    refreshed_at: datetime