from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    __tablename__ = "saas_tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180))
    billing_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    users: Mapped[list["User"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    __tablename__ = "saas_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("saas_tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(600))
    display_name: Mapped[str] = mapped_column(String(180))
    role: Mapped[str] = mapped_column(String(30), default="owner", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    tenant: Mapped[Tenant] = relationship(back_populates="users")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    youtube_connection: Mapped["YouTubeConnection | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )


class UserSession(Base):
    __tablename__ = "saas_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("saas_users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")


class YouTubeConnection(Base):
    __tablename__ = "saas_youtube_connections"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("saas_users.id"), unique=True, index=True)
    token_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    oauth_state: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    code_verifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    channel_title: Mapped[str | None] = mapped_column(String(250), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="youtube_connection")


class SourceVideo(Base):
    __tablename__ = "saas_source_videos"
    __table_args__ = (UniqueConstraint("user_id", "youtube_id", name="uq_saas_user_youtube_video"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("saas_tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("saas_users.id"), index=True)
    youtube_id: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(500))
    channel_title: Mapped[str] = mapped_column(String(250), default="")
    original_url: Mapped[str] = mapped_column(String(800))
    thumbnail_url: Mapped[str] = mapped_column(String(800), default="")
    rights_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    jobs: Mapped[list["Job"]] = relationship(back_populates="source_video", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "saas_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("saas_tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("saas_users.id"), index=True)
    source_video_id: Mapped[int] = mapped_column(ForeignKey("saas_source_videos.id"), index=True)
    requested_clips: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    source_video: Mapped[SourceVideo] = relationship(back_populates="jobs")
    clips: Mapped[list["Clip"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Clip(Base):
    __tablename__ = "saas_clips"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("saas_tenants.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("saas_users.id"), index=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("saas_jobs.id"), index=True)
    start_seconds: Mapped[float] = mapped_column(Float)
    end_seconds: Mapped[float] = mapped_column(Float)
    hook: Mapped[str] = mapped_column(String(500), default="")
    reason: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    copy_text: Mapped[str] = mapped_column(Text, default="")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    file_path: Mapped[str] = mapped_column(String(1000))
    subtitle_path: Mapped[str] = mapped_column(String(1000), default="")
    status: Mapped[str] = mapped_column(String(40), default="ready", index=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    upload_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    upload_privacy: Mapped[str] = mapped_column(String(20), default="private")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    job: Mapped[Job] = relationship(back_populates="clips")
