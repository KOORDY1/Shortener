from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_job_or_404
from app.db.models import Job
from app.db.session import get_db
from app.schemas import JobListResponse, JobResponse

router = APIRouter(tags=["jobs"])


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobResponse:
    return JobResponse.from_model(get_job_or_404(db, job_id))


@router.get("/jobs", response_model=JobListResponse)
def list_jobs(
    episode_id: str | None = None,
    candidate_id: str | None = None,
    job_type: str | None = Query(
        default=None, description="Filter by job type, e.g. analysis, script_generation"
    ),
    status: str | None = Query(
        default=None, description="Filter by status: queued, running, succeeded, failed"
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> JobListResponse:
    query = select(Job).order_by(Job.created_at.desc())
    count_query = select(func.count(Job.id))

    if episode_id:
        query = query.where(Job.episode_id == episode_id)
        count_query = count_query.where(Job.episode_id == episode_id)
    if candidate_id:
        query = query.where(Job.candidate_id == candidate_id)
        count_query = count_query.where(Job.candidate_id == candidate_id)
    if job_type:
        query = query.where(Job.type == job_type)
        count_query = count_query.where(Job.type == job_type)
    if status:
        query = query.where(Job.status == status)
        count_query = count_query.where(Job.status == status)

    total = db.scalar(count_query) or 0
    items = list(db.scalars(query.offset((page - 1) * page_size).limit(page_size)))
    return JobListResponse(items=[JobResponse.from_model(item) for item in items], total=total)
