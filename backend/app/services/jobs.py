from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import Job, JobStatus


def create_job(
    db: Session,
    *,
    job_type: str,
    episode_id: str | None = None,
    candidate_id: str | None = None,
    payload: dict | None = None,
) -> Job:
    job = Job(
        type=job_type,
        episode_id=episode_id,
        candidate_id=candidate_id,
        status=JobStatus.QUEUED.value,
        payload_json=payload or {},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_job_running(db: Session, job: Job, *, step: str, progress_percent: int) -> Job:
    job.status = JobStatus.RUNNING.value
    job.current_step = step
    job.progress_percent = progress_percent
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_job_succeeded(db: Session, job: Job, *, payload: dict | None = None) -> Job:
    job.status = JobStatus.SUCCEEDED.value
    job.current_step = "completed"
    job.progress_percent = 100
    if payload is not None:
        job.payload_json = payload
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def mark_job_failed(db: Session, job: Job, *, step: str, error_message: str) -> Job:
    job.status = JobStatus.FAILED.value
    job.current_step = step
    job.error_message = error_message
    db.add(job)
    db.commit()
    db.refresh(job)
    return job
