from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_candidate_or_404
from app.api.v1.candidate_read import _build_feedback_summary
from app.db.models import CandidateStatus
from app.db.session import get_db
from app.schemas import CandidateDetailResponse, CandidateRejectRequest, CandidateSelectionRequest
from app.services.analysis_service import candidate_segments, candidate_shots

router = APIRouter(tags=["candidates"])


@router.post("/candidates/{candidate_id}/select", response_model=CandidateDetailResponse)
def select_candidate(
    candidate_id: str,
    request: CandidateSelectionRequest,
    db: Session = Depends(get_db),
) -> CandidateDetailResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    candidate.selected = request.selected
    candidate.status = (
        CandidateStatus.SELECTED.value if request.selected else CandidateStatus.GENERATED.value
    )
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return CandidateDetailResponse.from_model(
        candidate,
        candidate_segments(db, candidate),
        candidate_shots(db, candidate),
        _build_feedback_summary(db, candidate_id),
    )


@router.post("/candidates/{candidate_id}/reject", response_model=CandidateDetailResponse)
def reject_candidate(
    candidate_id: str,
    request: CandidateRejectRequest,
    db: Session = Depends(get_db),
) -> CandidateDetailResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    candidate.status = CandidateStatus.REJECTED.value
    candidate.selected = False
    metadata = dict(candidate.metadata_json or {})
    rejection_reasons = list(metadata.get("rejection_reasons") or [])
    rejection_reasons.append(request.reason)
    metadata["rejection_reasons"] = rejection_reasons
    candidate.metadata_json = metadata
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return CandidateDetailResponse.from_model(
        candidate,
        candidate_segments(db, candidate),
        candidate_shots(db, candidate),
        _build_feedback_summary(db, candidate_id),
    )
