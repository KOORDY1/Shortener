from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Candidate, CandidateStatus, Episode, Job, JobType, ScriptDraft, TranscriptSegment
from app.db.session import get_db
from app.schemas import (
    AnalyzeRequest,
    CandidateDetailResponse,
    CandidateListResponse,
    CandidateRejectRequest,
    CandidateSelectionRequest,
    CandidateSummary,
    EpisodeCreateResponse,
    EpisodeDetailResponse,
    EpisodeListResponse,
    EpisodeSummary,
    EpisodeTimelineResponse,
    JobResponse,
    JobListResponse,
    ScriptDraftCreateRequest,
    ScriptDraftListResponse,
    ScriptDraftResponse,
    ScriptDraftUpdateRequest,
    ShotResponse,
    TranscriptSegmentResponse,
    TriggerJobResponse,
)
from app.services.analysis_service import candidate_segments, candidate_shots
from app.services.jobs import create_job
from app.services.storage_service import save_upload
from app.tasks.pipelines import launch_analysis_pipeline, launch_script_generation


router = APIRouter()


def get_episode_or_404(db: Session, episode_id: str) -> Episode:
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


def get_candidate_or_404(db: Session, candidate_id: str) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


def get_job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/episodes", response_model=EpisodeCreateResponse)
async def create_episode(
    show_title: str = Form(...),
    season_number: int | None = Form(default=None),
    episode_number: int | None = Form(default=None),
    episode_title: str | None = Form(default=None),
    original_language: str = Form(default="en"),
    target_channel: str = Form(default="kr_us_drama"),
    video_file: UploadFile = File(...),
    subtitle_file: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
) -> EpisodeCreateResponse:
    video_suffix = Path(video_file.filename or "source.mp4").suffix or ".mp4"
    subtitle_suffix = Path(subtitle_file.filename).suffix if subtitle_file and subtitle_file.filename else ".srt"

    episode = Episode(
        show_title=show_title,
        season_number=season_number,
        episode_number=episode_number,
        episode_title=episode_title,
        original_language=original_language,
        target_channel=target_channel,
        source_video_path="pending",
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)

    episode.source_video_path = save_upload(episode.id, video_file, "source", f"source{video_suffix}")
    if subtitle_file is not None:
        episode.source_subtitle_path = save_upload(episode.id, subtitle_file, "source", f"source{subtitle_suffix}")

    db.add(episode)
    db.commit()
    db.refresh(episode)
    return EpisodeCreateResponse.from_model(episode)


@router.get("/episodes", response_model=EpisodeListResponse)
def list_episodes(
    status: str | None = None,
    show_title: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
) -> EpisodeListResponse:
    query = select(Episode).order_by(Episode.created_at.desc())
    count_query = select(func.count(Episode.id))

    if status:
        query = query.where(Episode.status == status)
        count_query = count_query.where(Episode.status == status)
    if show_title:
        ilike_value = f"%{show_title}%"
        query = query.where(Episode.show_title.ilike(ilike_value))
        count_query = count_query.where(Episode.show_title.ilike(ilike_value))

    items = list(
        db.scalars(
            query.offset((page - 1) * page_size).limit(page_size)
        )
    )
    total = db.scalar(count_query) or 0
    return EpisodeListResponse(
        items=[EpisodeSummary.from_model(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/episodes/{episode_id}", response_model=EpisodeDetailResponse)
def get_episode(episode_id: str, db: Session = Depends(get_db)) -> EpisodeDetailResponse:
    return EpisodeDetailResponse.from_model(get_episode_or_404(db, episode_id))


@router.post("/episodes/{episode_id}/analyze", response_model=TriggerJobResponse)
def analyze_episode(
    episode_id: str,
    request: AnalyzeRequest,
    db: Session = Depends(get_db),
) -> TriggerJobResponse:
    episode = get_episode_or_404(db, episode_id)
    job = create_job(
        db,
        job_type=JobType.ANALYSIS.value,
        episode_id=episode.id,
        payload={"force_reanalyze": request.force_reanalyze},
    )
    launch_analysis_pipeline(episode_id=episode.id, job_id=job.id)
    db.refresh(job)
    return TriggerJobResponse(
        episode_id=episode.id,
        job_id=job.id,
        status=job.status,
        message="Analysis pipeline started",
    )


@router.get("/episodes/{episode_id}/timeline", response_model=EpisodeTimelineResponse)
def get_episode_timeline(episode_id: str, db: Session = Depends(get_db)) -> EpisodeTimelineResponse:
    episode = get_episode_or_404(db, episode_id)
    return EpisodeTimelineResponse(
        episode_id=episode.id,
        shots=[ShotResponse.from_model(item) for item in sorted(episode.shots, key=lambda item: item.shot_index)],
        transcript_segments=[
            TranscriptSegmentResponse.from_model(item)
            for item in sorted(episode.transcript_segments, key=lambda item: item.segment_index)
        ],
    )


@router.get("/episodes/{episode_id}/jobs", response_model=JobListResponse)
def list_episode_jobs(episode_id: str, db: Session = Depends(get_db)) -> JobListResponse:
    get_episode_or_404(db, episode_id)
    items = list(
        db.scalars(
            select(Job)
            .where(Job.episode_id == episode_id)
            .order_by(Job.created_at.desc())
        )
    )
    return JobListResponse(items=[JobResponse.from_model(item) for item in items], total=len(items))


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobResponse:
    return JobResponse.from_model(get_job_or_404(db, job_id))


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    episode_id: str | None = None,
    candidate_id: str | None = None,
    db: Session = Depends(get_db),
) -> JobListResponse:
    query = select(Job).order_by(Job.created_at.desc())
    if episode_id:
        query = query.where(Job.episode_id == episode_id)
    if candidate_id:
        query = query.where(Job.candidate_id == candidate_id)
    items = list(db.scalars(query))
    return JobListResponse(items=[JobResponse.from_model(item) for item in items], total=len(items))


@router.get("/episodes/{episode_id}/candidates", response_model=CandidateListResponse)
def list_episode_candidates(
    episode_id: str,
    candidate_type: str | None = Query(default=None, alias="type"),
    status: str | None = None,
    risk_level: str | None = None,
    min_score: float | None = None,
    sort_by: str = "total_score",
    order: str = "desc",
    db: Session = Depends(get_db),
) -> CandidateListResponse:
    get_episode_or_404(db, episode_id)
    query = select(Candidate).where(Candidate.episode_id == episode_id)
    if candidate_type:
        query = query.where(Candidate.type == candidate_type)
    if status:
        query = query.where(Candidate.status == status)
    if risk_level:
        query = query.where(Candidate.risk_level == risk_level)
    if min_score is not None:
        query = query.where(Candidate.total_score >= min_score)

    sortable_columns = {
        "total_score": Candidate.total_score,
        "risk_score": Candidate.risk_score,
        "start_time": Candidate.start_time,
    }
    sort_column = sortable_columns.get(sort_by, Candidate.total_score)
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())

    items = list(db.scalars(query))
    return CandidateListResponse(items=[CandidateSummary.from_model(item) for item in items], total=len(items))


@router.get("/candidates/{candidate_id}", response_model=CandidateDetailResponse)
def get_candidate(candidate_id: str, db: Session = Depends(get_db)) -> CandidateDetailResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    segments = candidate_segments(db, candidate)
    shots = candidate_shots(db, candidate)
    return CandidateDetailResponse.from_model(candidate, segments, shots)


@router.post("/candidates/{candidate_id}/select", response_model=CandidateDetailResponse)
def select_candidate(
    candidate_id: str,
    request: CandidateSelectionRequest,
    db: Session = Depends(get_db),
) -> CandidateDetailResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    candidate.selected = request.selected
    candidate.status = CandidateStatus.SELECTED.value if request.selected else CandidateStatus.GENERATED.value
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return CandidateDetailResponse.from_model(
        candidate,
        candidate_segments(db, candidate),
        candidate_shots(db, candidate),
    )


@router.post("/candidates/{candidate_id}/reject", response_model=CandidateDetailResponse)
def reject_candidate(
    candidate_id: str,
    request: CandidateRejectRequest,
    db: Session = Depends(get_db),
) -> CandidateDetailResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    reasons = list(candidate.risk_reasons or [])
    reasons.append(request.reason)
    candidate.status = CandidateStatus.REJECTED.value
    candidate.selected = False
    candidate.risk_reasons = reasons
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return CandidateDetailResponse.from_model(
        candidate,
        candidate_segments(db, candidate),
        candidate_shots(db, candidate),
    )


@router.post("/candidates/{candidate_id}/script-drafts", response_model=TriggerJobResponse)
def create_script_drafts(
    candidate_id: str,
    request: ScriptDraftCreateRequest,
    db: Session = Depends(get_db),
) -> TriggerJobResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    job = create_job(
        db,
        job_type=JobType.SCRIPT_GENERATION.value,
        episode_id=candidate.episode_id,
        candidate_id=candidate.id,
        payload=request.model_dump(),
    )
    launch_script_generation(
        candidate_id=candidate.id,
        job_id=job.id,
        language=request.language,
        versions=request.versions,
        tone=request.tone,
        channel_style=request.channel_style,
        force_regenerate=request.force_regenerate,
    )
    db.refresh(job)
    return TriggerJobResponse(candidate_id=candidate.id, job_id=job.id, status=job.status)


@router.get("/candidates/{candidate_id}/script-drafts", response_model=ScriptDraftListResponse)
def list_script_drafts(candidate_id: str, db: Session = Depends(get_db)) -> ScriptDraftListResponse:
    get_candidate_or_404(db, candidate_id)
    items = list(
        db.scalars(
            select(ScriptDraft)
            .where(ScriptDraft.candidate_id == candidate_id)
            .order_by(ScriptDraft.version_no.asc())
        )
    )
    return ScriptDraftListResponse(items=[ScriptDraftResponse.from_model(item) for item in items])


@router.patch("/script-drafts/{script_draft_id}", response_model=ScriptDraftResponse)
def update_script_draft(
    script_draft_id: str,
    request: ScriptDraftUpdateRequest,
    db: Session = Depends(get_db),
) -> ScriptDraftResponse:
    draft = db.get(ScriptDraft, script_draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Script draft not found")

    if request.hook_text is not None:
        draft.hook_text = request.hook_text
    if request.body_text is not None:
        draft.body_text = request.body_text
    if request.cta_text is not None:
        draft.cta_text = request.cta_text
    if request.title_options is not None:
        draft.title_options = request.title_options

    draft.full_script_text = " ".join(
        part for part in [draft.hook_text, draft.body_text, draft.cta_text] if part
    )
    draft.estimated_duration_seconds = round(max(15.0, len(draft.full_script_text) / 12), 2)
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return ScriptDraftResponse.from_model(draft)


@router.post("/script-drafts/{script_draft_id}/select", response_model=ScriptDraftResponse)
def select_script_draft(script_draft_id: str, db: Session = Depends(get_db)) -> ScriptDraftResponse:
    draft = db.get(ScriptDraft, script_draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Script draft not found")

    sibling_drafts = list(
        db.scalars(select(ScriptDraft).where(ScriptDraft.candidate_id == draft.candidate_id))
    )
    for item in sibling_drafts:
        item.is_selected = item.id == draft.id
        db.add(item)

    db.commit()
    db.refresh(draft)
    return ScriptDraftResponse.from_model(draft)
