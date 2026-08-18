from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SourceVideo(Base):
    __tablename__ = "source_videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    youtube_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    channel_title: Mapped[str] = mapped_column(String(250), default="")
    original_url: Mapped[str] = mapped_column(String(800))
    thumbnail_url: Mapped[str] = mapped_column(String(800), default="")
    rights_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    jobs: Mapped[list["Job"]] = relationship(back_populates="source_video", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_video_id: Mapped[int] = mapped_column(ForeignKey("source_videos.id"), index=True)
    requested_clips: Mapped[int] = mapped_column(Integer, default=3)
    status: Mapped[str] = mapped_column(String(40), default="queued", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    source_video: Mapped[SourceVideo] = relationship(back_populates="jobs")
    clips: Mapped[list["Clip"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
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
