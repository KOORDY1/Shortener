from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_episode_or_404
from app.db.models import Candidate, Episode, Job, JobType
from app.db.session import get_db
from app.schemas import (
    AnalyzeRequest,
    CandidateListResponse,
    CandidateSummary,
    EpisodeCreateResponse,
    EpisodeDetailResponse,
    EpisodeListResponse,
    EpisodeSummary,
    EpisodeTimelineResponse,
    JobListResponse,
    JobResponse,
    ShotResponse,
    TranscriptSegmentResponse,
    TriggerJobResponse,
)
from app.services.jobs import create_job
from app.services.storage_service import save_upload
from app.tasks.pipelines import launch_analysis_pipeline

router = APIRouter(tags=["episodes"])


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

    items = list(db.scalars(query.offset((page - 1) * page_size).limit(page_size)))
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
            select(Job).where(Job.episode_id == episode_id).order_by(Job.created_at.desc())
        )
    )
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
