from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_episode_or_404
from app.core.config import get_settings
from app.db.models import Candidate, Episode, Job, JobType, TranscriptSegment
from app.db.session import get_db
from app.schemas import (
    AnalyzeRequest,
    CandidateListResponse,
    CandidateSummary,
    EpisodeCreateResponse,
    EpisodeDetailResponse,
    EpisodeListResponse,
    EpisodeOperationOkResponse,
    EpisodeSummary,
    EpisodeTimelineResponse,
    JobListResponse,
    JobResponse,
    ShotResponse,
    TranscriptSegmentPatchRequest,
    TranscriptSegmentResponse,
    TriggerJobResponse,
)
from app.services.episode_cleanup import (
    clear_episode_analysis,
    clear_episode_cache,
    delete_episode_storage,
)
from app.services.jobs import create_job
from app.services.storage_service import episode_root, save_upload
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
    subtitle_suffix = (
        Path(subtitle_file.filename).suffix if subtitle_file and subtitle_file.filename else ".srt"
    )

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

    episode.source_video_path = save_upload(
        episode.id, video_file, "source", f"source{video_suffix}"
    )
    if subtitle_file is not None:
        episode.source_subtitle_path = save_upload(
            episode.id, subtitle_file, "source", f"source{subtitle_suffix}"
        )

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


@router.delete("/episodes/{episode_id}", status_code=204)
def delete_episode(episode_id: str, db: Session = Depends(get_db)) -> Response:
    episode = get_episode_or_404(db, episode_id)
    db.delete(episode)
    db.commit()
    delete_episode_storage(episode_id)
    return Response(status_code=204)


@router.post("/episodes/{episode_id}/clear-analysis", response_model=EpisodeOperationOkResponse)
def clear_analysis_for_episode(
    episode_id: str, db: Session = Depends(get_db)
) -> EpisodeOperationOkResponse:
    get_episode_or_404(db, episode_id)
    clear_episode_analysis(db, episode_id)
    return EpisodeOperationOkResponse(
        message="분석 결과(후보·샷·대본·작업 기록·렌더 산출물)를 삭제했습니다. 원본 업로드와 분석 가속용 캐시는 유지됩니다. 다시 분석할 수 있습니다.",
    )


@router.post("/episodes/{episode_id}/clear-cache", response_model=EpisodeOperationOkResponse)
def clear_cache_for_episode(
    episode_id: str, db: Session = Depends(get_db)
) -> EpisodeOperationOkResponse:
    get_episode_or_404(db, episode_id)
    clear_episode_cache(db, episode_id)
    return EpisodeOperationOkResponse(
        message="분석 가속용 캐시(proxy/audio/shots/cache)를 삭제했습니다. 현재 후보/대본은 유지되지만 샷 타임라인과 캐시 기반 미리보기는 다음 재분석 전까지 비어 있을 수 있습니다.",
    )


@router.get("/episodes/{episode_id}", response_model=EpisodeDetailResponse)
def get_episode(episode_id: str, db: Session = Depends(get_db)) -> EpisodeDetailResponse:
    return EpisodeDetailResponse.from_model(get_episode_or_404(db, episode_id))


@router.get("/episodes/{episode_id}/source-video")
def stream_episode_source_video(episode_id: str, db: Session = Depends(get_db)) -> FileResponse:
    """에피소드 업로드 원본 영상(로컬 스토리지)을 브라우저에서 재생하기 위한 스트리밍."""
    episode = get_episode_or_404(db, episode_id)
    settings = get_settings()
    raw = Path(episode.source_video_path).expanduser()
    path = raw.resolve() if raw.is_absolute() else (settings.resolved_storage_root / raw).resolve()
    allowed = episode_root(episode_id).resolve()
    try:
        path.relative_to(allowed)
    except ValueError:
        raise HTTPException(status_code=404, detail="Video path outside episode storage") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")

    suffix = path.suffix.lower()
    media_types = {
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".m4v": "video/x-m4v",
    }
    media_type = media_types.get(suffix, "application/octet-stream")
    return FileResponse(path, media_type=media_type, filename=path.name)


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
        payload={
            "force_reanalyze": request.force_reanalyze,
            "ignore_cache": request.ignore_cache,
        },
    )
    launch_analysis_pipeline(
        episode_id=episode.id,
        job_id=job.id,
        ignore_cache=request.ignore_cache,
    )
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
        shots=[
            ShotResponse.from_model(item)
            for item in sorted(episode.shots, key=lambda item: item.shot_index)
        ],
        transcript_segments=[
            TranscriptSegmentResponse.from_model(item)
            for item in sorted(episode.transcript_segments, key=lambda item: item.segment_index)
        ],
    )


@router.get("/episodes/{episode_id}/jobs", response_model=JobListResponse)
def list_episode_jobs(episode_id: str, db: Session = Depends(get_db)) -> JobListResponse:
    get_episode_or_404(db, episode_id)
    items = list(
        db.scalars(select(Job).where(Job.episode_id == episode_id).order_by(Job.created_at.desc()))
    )
    return JobListResponse(items=[JobResponse.from_model(item) for item in items], total=len(items))


@router.get("/episodes/{episode_id}/candidates", response_model=CandidateListResponse)
def list_episode_candidates(
    episode_id: str,
    candidate_type: str | None = Query(default=None, alias="type"),
    status: str | None = None,
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
    if min_score is not None:
        query = query.where(Candidate.total_score >= min_score)

    sortable_columns = {
        "total_score": Candidate.total_score,
        "start_time": Candidate.start_time,
    }
    sort_column = sortable_columns.get(sort_by, Candidate.total_score)
    query = query.order_by(sort_column.asc() if order == "asc" else sort_column.desc())

    items = list(db.scalars(query))
    return CandidateListResponse(
        items=[CandidateSummary.from_model(item) for item in items], total=len(items)
    )


@router.patch(
    "/transcript-segments/{segment_id}",
    response_model=TranscriptSegmentResponse,
    tags=["transcript"],
)
def patch_transcript_segment(
    segment_id: str,
    request: TranscriptSegmentPatchRequest,
    db: Session = Depends(get_db),
) -> TranscriptSegmentResponse:
    segment = db.get(TranscriptSegment, segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail="TranscriptSegment not found")
    segment.text = request.text
    db.add(segment)
    db.commit()
    db.refresh(segment)
    return TranscriptSegmentResponse.from_model(segment)
