from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def new_id() -> str:
    return str(uuid4())


class EpisodeStatus(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class JobType(str, Enum):
    ANALYSIS = "analysis"
    SCRIPT_GENERATION = "script_generation"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CandidateStatus(str, Enum):
    GENERATED = "generated"
    SELECTED = "selected"
    REJECTED = "rejected"
    DRAFTED = "drafted"


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    show_title: Mapped[str] = mapped_column(String(255))
    season_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    episode_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_language: Mapped[str] = mapped_column(String(20), default="en")
    target_channel: Mapped[str] = mapped_column(String(50), default="kr_us_drama")
    status: Mapped[str] = mapped_column(String(32), default=EpisodeStatus.UPLOADED.value)
    source_video_path: Mapped[str] = mapped_column(Text)
    source_subtitle_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxy_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    fps: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    jobs: Mapped[list["Job"]] = relationship(back_populates="episode", cascade="all, delete-orphan")
    shots: Mapped[list["Shot"]] = relationship(back_populates="episode", cascade="all, delete-orphan")
    transcript_segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="episode",
        cascade="all, delete-orphan",
    )
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="episode", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    episode_id: Mapped[str | None] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"), nullable=True)
    candidate_id: Mapped[str | None] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=True)
    type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default=JobStatus.QUEUED.value)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column("payload", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    episode: Mapped[Episode | None] = relationship(back_populates="jobs")
    candidate: Mapped["Candidate | None"] = relationship(back_populates="jobs")


class Shot(Base):
    __tablename__ = "shots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"))
    shot_index: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    episode: Mapped[Episode] = relationship(back_populates="shots")


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"))
    segment_index: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    text: Mapped[str] = mapped_column(Text)
    speaker_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    episode: Mapped[Episode] = relationship(back_populates="transcript_segments")


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id", ondelete="CASCADE"))
    candidate_index: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(64), default="context_commentary")
    status: Mapped[str] = mapped_column(String(32), default=CandidateStatus.GENERATED.value)
    title_hint: Mapped[str] = mapped_column(String(255))
    start_time: Mapped[float] = mapped_column(Float)
    end_time: Mapped[float] = mapped_column(Float)
    duration_seconds: Mapped[float] = mapped_column(Float)
    total_score: Mapped[float] = mapped_column(Float, default=0)
    risk_score: Mapped[float] = mapped_column(Float, default=0)
    risk_level: Mapped[str] = mapped_column(String(16), default="low")
    scores_json: Mapped[dict[str, Any]] = mapped_column("scores", JSON, default=dict)
    risk_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    episode: Mapped[Episode] = relationship(back_populates="candidates")
    script_drafts: Mapped[list["ScriptDraft"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    jobs: Mapped[list[Job]] = relationship(back_populates="candidate")


class ScriptDraft(Base):
    __tablename__ = "script_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"))
    version_no: Mapped[int] = mapped_column(Integer, default=1)
    language: Mapped[str] = mapped_column(String(16), default="ko")
    hook_text: Mapped[str] = mapped_column(Text)
    body_text: Mapped[str] = mapped_column(Text)
    cta_text: Mapped[str] = mapped_column(Text)
    full_script_text: Mapped[str] = mapped_column(Text)
    estimated_duration_seconds: Mapped[float] = mapped_column(Float, default=0)
    title_options: Mapped[list[str]] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    candidate: Mapped[Candidate] = relationship(back_populates="script_drafts")
