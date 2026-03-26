from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_candidate_or_404
from app.db.models import JobType, ScriptDraft
from app.db.session import get_db
from app.schemas import (
    ScriptDraftCreateRequest,
    ScriptDraftListResponse,
    ScriptDraftResponse,
    TriggerJobResponse,
)
from app.services.jobs import create_job
from app.tasks.pipelines import launch_script_generation

router = APIRouter(tags=["candidates"])


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
