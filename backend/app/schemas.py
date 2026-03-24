from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models import Candidate, Episode, Job, ScriptDraft, Shot, TranscriptSegment


class EpisodeCreateResponse(BaseModel):
    id: str
    status: str
    show_title: str
    season_number: int | None
    episode_number: int | None
    target_channel: str
    created_at: datetime | None

    @classmethod
    def from_model(cls, episode: Episode) -> "EpisodeCreateResponse":
        return cls(
            id=episode.id,
            status=episode.status,
            show_title=episode.show_title,
            season_number=episode.season_number,
            episode_number=episode.episode_number,
            target_channel=episode.target_channel,
            created_at=episode.created_at,
        )


class EpisodeSummary(BaseModel):
    id: str
    show_title: str
    season_number: int | None
    episode_number: int | None
    episode_title: str | None
    target_channel: str
    status: str
    duration_seconds: float | None
    created_at: datetime | None

    @classmethod
    def from_model(cls, episode: Episode) -> "EpisodeSummary":
        return cls(
            id=episode.id,
            show_title=episode.show_title,
            season_number=episode.season_number,
            episode_number=episode.episode_number,
            episode_title=episode.episode_title,
            target_channel=episode.target_channel,
            status=episode.status,
            duration_seconds=episode.duration_seconds,
            created_at=episode.created_at,
        )


class EpisodeListResponse(BaseModel):
    items: list[EpisodeSummary]
    page: int
    page_size: int
    total: int


class EpisodeDetailResponse(BaseModel):
    id: str
    show_title: str
    season_number: int | None
    episode_number: int | None
    episode_title: str | None
    original_language: str
    target_channel: str
    status: str
    source_video_path: str
    source_subtitle_path: str | None
    proxy_video_path: str | None
    audio_path: str | None
    duration_seconds: float | None
    fps: float | None
    width: int | None
    height: int | None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_model(cls, episode: Episode) -> "EpisodeDetailResponse":
        return cls(
            id=episode.id,
            show_title=episode.show_title,
            season_number=episode.season_number,
            episode_number=episode.episode_number,
            episode_title=episode.episode_title,
            original_language=episode.original_language,
            target_channel=episode.target_channel,
            status=episode.status,
            source_video_path=episode.source_video_path,
            source_subtitle_path=episode.source_subtitle_path,
            proxy_video_path=episode.proxy_video_path,
            audio_path=episode.audio_path,
            duration_seconds=episode.duration_seconds,
            fps=episode.fps,
            width=episode.width,
            height=episode.height,
            metadata=episode.metadata_json or {},
        )


class AnalyzeRequest(BaseModel):
    force_reanalyze: bool = False


class TriggerJobResponse(BaseModel):
    episode_id: str | None = None
    candidate_id: str | None = None
    job_id: str
    status: str
    message: str | None = None


class JobResponse(BaseModel):
    id: str
    episode_id: str | None
    candidate_id: str | None
    type: str
    status: str
    progress_percent: int
    current_step: str | None
    error_message: str | None
    payload: dict[str, Any]
    created_at: datetime | None
    updated_at: datetime | None

    @classmethod
    def from_model(cls, job: Job) -> "JobResponse":
        return cls(
            id=job.id,
            episode_id=job.episode_id,
            candidate_id=job.candidate_id,
            type=job.type,
            status=job.status,
            progress_percent=job.progress_percent,
            current_step=job.current_step,
            error_message=job.error_message,
            payload=job.payload_json or {},
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class JobListResponse(BaseModel):
    items: list[JobResponse]
    total: int


class ShotResponse(BaseModel):
    id: str
    shot_index: int
    start_time: float
    end_time: float
    thumbnail_path: str | None

    @classmethod
    def from_model(cls, shot: Shot) -> "ShotResponse":
        return cls(
            id=shot.id,
            shot_index=shot.shot_index,
            start_time=shot.start_time,
            end_time=shot.end_time,
            thumbnail_path=shot.thumbnail_path,
        )


class TranscriptSegmentResponse(BaseModel):
    id: str
    start_time: float
    end_time: float
    text: str
    speaker_label: str | None

    @classmethod
    def from_model(cls, segment: TranscriptSegment) -> "TranscriptSegmentResponse":
        return cls(
            id=segment.id,
            start_time=segment.start_time,
            end_time=segment.end_time,
            text=segment.text,
            speaker_label=segment.speaker_label,
        )


class EpisodeTimelineResponse(BaseModel):
    episode_id: str
    shots: list[ShotResponse]
    transcript_segments: list[TranscriptSegmentResponse]


class CandidateSummary(BaseModel):
    id: str
    candidate_index: int
    type: str
    status: str
    title_hint: str
    start_time: float
    end_time: float
    duration_seconds: float
    total_score: float
    risk_score: float
    risk_level: str

    @classmethod
    def from_model(cls, candidate: Candidate) -> "CandidateSummary":
        return cls(
            id=candidate.id,
            candidate_index=candidate.candidate_index,
            type=candidate.type,
            status=candidate.status,
            title_hint=candidate.title_hint,
            start_time=candidate.start_time,
            end_time=candidate.end_time,
            duration_seconds=candidate.duration_seconds,
            total_score=candidate.total_score,
            risk_score=candidate.risk_score,
            risk_level=candidate.risk_level,
        )


class CandidateListResponse(BaseModel):
    items: list[CandidateSummary]
    total: int


class CandidateDetailResponse(BaseModel):
    id: str
    episode_id: str
    type: str
    status: str
    title_hint: str
    start_time: float
    end_time: float
    duration_seconds: float
    scores: dict[str, Any]
    risk: dict[str, Any]
    metadata: dict[str, Any]
    shots: list[ShotResponse]
    transcript_segments: list[TranscriptSegmentResponse]

    @classmethod
    def from_model(
        cls,
        candidate: Candidate,
        segments: list[TranscriptSegment],
        shots: list[Shot],
    ) -> "CandidateDetailResponse":
        return cls(
            id=candidate.id,
            episode_id=candidate.episode_id,
            type=candidate.type,
            status=candidate.status,
            title_hint=candidate.title_hint,
            start_time=candidate.start_time,
            end_time=candidate.end_time,
            duration_seconds=candidate.duration_seconds,
            scores=candidate.scores_json or {},
            risk={
                "risk_score": candidate.risk_score,
                "risk_level": candidate.risk_level,
                "reasons": candidate.risk_reasons or [],
            },
            metadata=candidate.metadata_json or {},
            shots=[ShotResponse.from_model(item) for item in shots],
            transcript_segments=[TranscriptSegmentResponse.from_model(item) for item in segments],
        )


class CandidateSelectionRequest(BaseModel):
    selected: bool = True


class CandidateRejectRequest(BaseModel):
    reason: str


class ScriptDraftCreateRequest(BaseModel):
    language: str = "ko"
    versions: int = 2
    tone: str = "sharp_explanatory"
    channel_style: str = "kr_us_drama"
    force_regenerate: bool = False


class ScriptDraftUpdateRequest(BaseModel):
    hook_text: str | None = None
    body_text: str | None = None
    cta_text: str | None = None
    title_options: list[str] | None = None


class ScriptDraftResponse(BaseModel):
    id: str
    version_no: int
    language: str
    hook_text: str
    body_text: str
    cta_text: str
    full_script_text: str
    estimated_duration_seconds: float
    title_options: list[str]
    is_selected: bool

    @classmethod
    def from_model(cls, script_draft: ScriptDraft) -> "ScriptDraftResponse":
        return cls(
            id=script_draft.id,
            version_no=script_draft.version_no,
            language=script_draft.language,
            hook_text=script_draft.hook_text,
            body_text=script_draft.body_text,
            cta_text=script_draft.cta_text,
            full_script_text=script_draft.full_script_text,
            estimated_duration_seconds=script_draft.estimated_duration_seconds,
            title_options=script_draft.title_options or [],
            is_selected=script_draft.is_selected,
        )


class ScriptDraftListResponse(BaseModel):
    items: list[ScriptDraftResponse]
