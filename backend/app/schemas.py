from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.models import (
    Candidate,
    CandidateFeedback,
    Episode,
    Export,
    FailureType,
    FeedbackAction,
    Job,
    ScriptDraft,
    Shot,
    TranscriptSegment,
    VideoDraft,
)
from app.services.candidate_spans import candidate_clip_spans, is_composite_candidate


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
    ignore_cache: bool = False


class TriggerJobResponse(BaseModel):
    episode_id: str | None = None
    candidate_id: str | None = None
    job_id: str | None = None
    video_draft_id: str | None = None
    export_id: str | None = None
    status: str
    message: str | None = None


class EpisodeOperationOkResponse(BaseModel):
    ok: bool = True
    message: str


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
    composite: bool = False
    span_count: int = 1
    selected: bool = False
    failure_tags: list[str] = Field(default_factory=list)

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
            composite=is_composite_candidate(candidate),
            span_count=len(candidate_clip_spans(candidate)),
            selected=candidate.selected,
            failure_tags=list(candidate.failure_tags or []),
        )


class CandidateListResponse(BaseModel):
    items: list[CandidateSummary]
    total: int


class CandidateFeedbackSummary(BaseModel):
    """Candidate 상세 응답에 포함되는 피드백 요약."""

    feedback_count: int = 0
    latest_feedback_action: str | None = None
    latest_feedback_at: datetime | None = None
    latest_feedback_reason: str | None = None


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
    metadata: dict[str, Any]
    shots: list[ShotResponse]
    transcript_segments: list[TranscriptSegmentResponse]
    short_clip_path: str | None = None
    short_clip_error: str | None = None
    preview_clip_path: str | None = None
    preview_clip_error: str | None = None
    render_config: dict[str, Any] = Field(default_factory=dict)
    has_edited_ass: bool = False
    composite: bool = False
    primary_span_index: int = 0
    clip_spans: list[dict[str, Any]] = Field(default_factory=list)
    # 3순위: 직접 노출 필드
    selected: bool = False
    failure_tags: list[str] = Field(default_factory=list)
    feedback_summary: CandidateFeedbackSummary = Field(default_factory=CandidateFeedbackSummary)

    @classmethod
    def from_model(
        cls,
        candidate: Candidate,
        segments: list[TranscriptSegment],
        shots: list[Shot],
        feedback_summary: CandidateFeedbackSummary | None = None,
    ) -> "CandidateDetailResponse":
        meta = candidate.metadata_json or {}
        editor_meta = meta.get("render_editor") or {}
        clip_spans = candidate_clip_spans(candidate)
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
            metadata=meta,
            shots=[ShotResponse.from_model(item) for item in shots],
            transcript_segments=[TranscriptSegmentResponse.from_model(item) for item in segments],
            short_clip_path=candidate.short_clip_path,
            short_clip_error=meta.get("short_clip_error"),
            preview_clip_path=editor_meta.get("preview_clip_path"),
            preview_clip_error=editor_meta.get("preview_clip_error"),
            render_config=editor_meta.get("render_config") or {},
            has_edited_ass=bool(editor_meta.get("edited_ass_path")),
            composite=bool(meta.get("composite")),
            primary_span_index=int(meta.get("primary_span_index") or 0),
            clip_spans=clip_spans,
            selected=candidate.selected,
            failure_tags=list(candidate.failure_tags or []),
            feedback_summary=feedback_summary or CandidateFeedbackSummary(),
        )


class CandidateSelectionRequest(BaseModel):
    selected: bool = True


class CandidateRejectRequest(BaseModel):
    reason: str


class ShortClipSubtitleStyle(BaseModel):
    """libass 번인 스타일(편집기의 ‘자막 속성’에 가까운 옵션). Alignment는 ASS 규칙(2=하단 중앙)."""

    font_family: str = Field(default="Noto Sans CJK KR", max_length=120)
    font_size: int = Field(default=28, ge=10, le=80)
    alignment: int = Field(default=2, ge=1, le=9)
    margin_v: int = Field(default=52, ge=0, le=400)
    outline: int = Field(default=2, ge=0, le=8)
    primary_color: str = Field(default="#FFFFFF", max_length=16)
    outline_color: str = Field(default="#000000", max_length=16)
    shadow: int = Field(default=0, ge=0, le=8)
    background_box: bool = False
    bold: bool = False


class ShortClipSubtitleTextOverride(BaseModel):
    segment_id: str
    text: str = Field(max_length=4000)


class ShortClipRenderConfig(BaseModel):
    trim_start: float | None = None
    trim_end: float | None = None
    burn_subtitles: bool = True
    subtitle_source: Literal["none", "file", "transcript", "edited-ass"] = "file"
    aspect_ratio: Literal["9:16", "1:1", "16:9"] = "9:16"
    fit_mode: Literal["cover", "contain", "pad-blur"] = "contain"
    quality_preset: Literal["draft", "standard", "high"] = "standard"
    resolution_preset: str = "1080x1920"
    width: int = 1080
    height: int = 1920
    subtitle_style: ShortClipSubtitleStyle | None = None
    subtitle_text_overrides: list[ShortClipSubtitleTextOverride] | None = None
    use_imported_subtitles: bool = False
    use_edited_ass: bool = False


class ShortClipRenderRequest(ShortClipRenderConfig):
    """후보 구간을 프리셋 기반으로 렌더하거나 preview clip을 생성합니다."""

    output_kind: Literal["final", "preview"] = "final"
    edited_ass: str | None = Field(default=None, max_length=200_000)
    save_config: bool = True


class EditedAssPayload(BaseModel):
    content: str = Field(default="", max_length=200_000)


class EditedAssResponse(BaseModel):
    content: str
    has_content: bool = False


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
    metadata: dict[str, Any] = Field(default_factory=dict)

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
            metadata=script_draft.metadata_json or {},
        )


class ScriptDraftListResponse(BaseModel):
    items: list[ScriptDraftResponse]


class VideoDraftCreateRequest(BaseModel):
    script_draft_id: str
    template_type: str = "dramashorts_v1"
    tts_voice_key: str | None = "ko_female_01"
    burned_caption: bool = True
    render_config: dict[str, Any] | None = None


class VideoDraftSummary(BaseModel):
    id: str
    candidate_id: str
    script_draft_id: str
    version_no: int
    status: str
    template_type: str
    tts_voice_key: str | None
    draft_video_path: str | None
    thumbnail_path: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_model(cls, vd: VideoDraft) -> "VideoDraftSummary":
        return cls(
            id=vd.id,
            candidate_id=vd.candidate_id,
            script_draft_id=vd.script_draft_id,
            version_no=vd.version_no,
            status=vd.status,
            template_type=vd.template_type,
            tts_voice_key=vd.tts_voice_key,
            draft_video_path=vd.draft_video_path,
            thumbnail_path=vd.thumbnail_path,
            metadata=vd.metadata_json or {},
        )


class VideoDraftListResponse(BaseModel):
    items: list[VideoDraftSummary]
    total: int


class VideoDraftDetailResponse(BaseModel):
    id: str
    candidate_id: str
    script_draft_id: str
    version_no: int
    status: str
    template_type: str
    tts_voice_key: str | None
    aspect_ratio: str
    width: int
    height: int
    draft_video_path: str | None
    subtitle_path: str | None
    thumbnail_path: str | None
    burned_caption: bool
    render_config: dict[str, Any]
    timeline_json: dict[str, Any]
    operator_notes: str | None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_model(cls, vd: VideoDraft) -> "VideoDraftDetailResponse":
        return cls(
            id=vd.id,
            candidate_id=vd.candidate_id,
            script_draft_id=vd.script_draft_id,
            version_no=vd.version_no,
            status=vd.status,
            template_type=vd.template_type,
            tts_voice_key=vd.tts_voice_key,
            aspect_ratio=vd.aspect_ratio,
            width=vd.width,
            height=vd.height,
            draft_video_path=vd.draft_video_path,
            subtitle_path=vd.subtitle_path,
            thumbnail_path=vd.thumbnail_path,
            burned_caption=vd.burned_caption,
            render_config=vd.render_config_json or {},
            timeline_json=vd.timeline_json or {},
            operator_notes=vd.operator_notes,
            metadata=vd.metadata_json or {},
        )


class VideoDraftPatchRequest(BaseModel):
    operator_notes: str | None = None
    timeline_json: dict[str, Any] | None = None
    render_config: dict[str, Any] | None = None


class VideoDraftRejectRequest(BaseModel):
    reason: str | None = None


class ExportCreateRequest(BaseModel):
    export_preset: str = "shorts_default"
    include_srt: bool = True
    include_script_txt: bool = True
    include_metadata_json: bool = True


class ExportDetailResponse(BaseModel):
    id: str
    video_draft_id: str
    status: str
    export_preset: str
    export_video_path: str | None
    export_subtitle_path: str | None
    export_script_path: str | None
    export_metadata_path: str | None
    file_size_bytes: int | None
    metadata: dict[str, Any]

    @classmethod
    def from_model(cls, exp: Export) -> "ExportDetailResponse":
        return cls(
            id=exp.id,
            video_draft_id=exp.video_draft_id,
            status=exp.status,
            export_preset=exp.export_preset,
            export_video_path=exp.export_video_path,
            export_subtitle_path=exp.export_subtitle_path,
            export_script_path=exp.export_script_path,
            export_metadata_path=exp.export_metadata_path,
            file_size_bytes=exp.file_size_bytes,
            metadata=exp.metadata_json or {},
        )


# --- 실패 유형 태깅 ---

VALID_FAILURE_TYPES: frozenset[str] = frozenset(ft.value for ft in FailureType)
VALID_FEEDBACK_ACTIONS: frozenset[str] = frozenset(fa.value for fa in FeedbackAction)


class FailureTagRequest(BaseModel):
    failure_tags: list[str] = Field(default_factory=list, max_length=10)


class FailureTagResponse(BaseModel):
    id: str
    failure_tags: list[str]


# --- 운영자 피드백 로그 ---


class FeedbackMetadata(BaseModel):
    """피드백 요청 metadata — reordered 액션의 new_rank 등."""

    new_rank: int | None = None

    # 서버가 채우는 필드 (클라이언트 전송 불필요)
    reorder_from: int | None = None
    reorder_to: int | None = None
    episode_candidate_count: int | None = None
    episode_selected_count: int | None = None


class CandidateFeedbackCreateRequest(BaseModel):
    action: str  # FeedbackAction value
    reason: str | None = None
    # 항상 존재 — []=clear, ["tag",...]=overwrite+dedupe. 항상 Candidate.failure_tags와 동기화.
    failure_tags: list[str] = Field(default_factory=list)
    metadata: FeedbackMetadata = Field(default_factory=FeedbackMetadata)


class CandidateFeedbackSnapshotField(BaseModel):
    status: str = ""
    selected: bool = False
    candidate_index: int = 0
    total_score: float = 0.0
    failure_tags: list[str] = Field(default_factory=list)


class CandidateFeedbackResponse(BaseModel):
    id: str
    candidate_id: str
    action: str
    reason: str | None
    failure_tags: list[str]
    before_snapshot: CandidateFeedbackSnapshotField
    after_snapshot: CandidateFeedbackSnapshotField
    metadata: dict[str, str | int | float | bool | None]
    created_at: datetime | None

    @classmethod
    def from_model(cls, fb: CandidateFeedback) -> "CandidateFeedbackResponse":
        def _parse_snapshot(raw: dict[str, str | int | float | bool | list[str]] | None) -> CandidateFeedbackSnapshotField:
            if not raw:
                return CandidateFeedbackSnapshotField()
            try:
                return CandidateFeedbackSnapshotField(
                    status=str(raw.get("status", "")),
                    selected=bool(raw.get("selected", False)),
                    candidate_index=int(raw.get("candidate_index", 0)),
                    total_score=float(raw.get("total_score", 0.0)),
                    failure_tags=list(raw.get("failure_tags") or []),
                )
            except (ValueError, TypeError):
                return CandidateFeedbackSnapshotField()

        raw_meta = fb.metadata_json or {}
        safe_meta: dict[str, str | int | float | bool | None] = {
            k: v for k, v in raw_meta.items()
            if isinstance(v, (str, int, float, bool, type(None)))
        }

        return cls(
            id=fb.id,
            candidate_id=fb.candidate_id,
            action=fb.action,
            reason=fb.reason,
            failure_tags=fb.failure_tags or [],
            before_snapshot=_parse_snapshot(fb.before_snapshot),
            after_snapshot=_parse_snapshot(fb.after_snapshot),
            metadata=safe_meta,
            created_at=fb.created_at,
        )


class CandidateFeedbackListResponse(BaseModel):
    items: list[CandidateFeedbackResponse]
    total: int
