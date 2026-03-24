from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_candidate_or_404, get_script_draft_or_404
from app.db.models import Candidate, CandidateStatus, JobType, ScriptDraft, VideoDraft
from app.db.session import get_db
from app.schemas import (
    CandidateDetailResponse,
    CandidateRejectRequest,
    CandidateSelectionRequest,
    ScriptDraftCreateRequest,
    ScriptDraftListResponse,
    ScriptDraftResponse,
    TriggerJobResponse,
    VideoDraftCreateRequest,
    VideoDraftListResponse,
    VideoDraftSummary,
)
from app.services.analysis_service import candidate_segments, candidate_shots
from app.services.jobs import create_job
from app.services.video_draft_service import create_mock_video_draft
from app.tasks.pipelines import launch_script_generation

router = APIRouter(tags=["candidates"])


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


@router.get("/candidates/{candidate_id}/video-drafts", response_model=VideoDraftListResponse)
def list_candidate_video_drafts(candidate_id: str, db: Session = Depends(get_db)) -> VideoDraftListResponse:
    get_candidate_or_404(db, candidate_id)
    items = list(
        db.scalars(
            select(VideoDraft)
            .where(VideoDraft.candidate_id == candidate_id)
            .order_by(VideoDraft.version_no.desc())
        )
    )
    return VideoDraftListResponse(items=[VideoDraftSummary.from_model(item) for item in items], total=len(items))


@router.post("/candidates/{candidate_id}/video-drafts", response_model=TriggerJobResponse)
def create_candidate_video_draft(
    candidate_id: str,
    request: VideoDraftCreateRequest,
    db: Session = Depends(get_db),
) -> TriggerJobResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    script_draft = get_script_draft_or_404(db, request.script_draft_id)
    if script_draft.candidate_id != candidate.id:
        raise HTTPException(status_code=400, detail="script_draft does not belong to this candidate")

    vd = create_mock_video_draft(
        db,
        candidate=candidate,
        script_draft=script_draft,
        template_type=request.template_type,
        tts_voice_key=request.tts_voice_key,
        burned_caption=request.burned_caption,
    )
    return TriggerJobResponse(
        candidate_id=candidate.id,
        video_draft_id=vd.id,
        status=vd.status,
        message="Mock video draft created (no render worker)",
    )
