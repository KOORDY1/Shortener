from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.v1.deps import get_candidate_or_404
from app.db.models import CandidateFeedback
from app.db.session import get_db
from app.schemas import (
    VALID_FAILURE_TYPES,
    VALID_FEEDBACK_ACTIONS,
    CandidateFeedbackCreateRequest,
    CandidateFeedbackListResponse,
    CandidateFeedbackResponse,
    FailureTagRequest,
    FailureTagResponse,
)

router = APIRouter(tags=["candidates"])


@router.put("/candidates/{candidate_id}/failure-tags", response_model=FailureTagResponse)
def set_failure_tags(
    candidate_id: str,
    request: FailureTagRequest,
    db: Session = Depends(get_db),
) -> FailureTagResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    invalid = [t for t in request.failure_tags if t not in VALID_FAILURE_TYPES]
    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"유효하지 않은 failure_type: {invalid}. 허용값: {sorted(VALID_FAILURE_TYPES)}",
        )
    candidate.failure_tags = list(dict.fromkeys(request.failure_tags))
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return FailureTagResponse(id=candidate.id, failure_tags=candidate.failure_tags or [])


@router.get("/candidates/{candidate_id}/failure-tags", response_model=FailureTagResponse)
def get_failure_tags(
    candidate_id: str,
    db: Session = Depends(get_db),
) -> FailureTagResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    return FailureTagResponse(id=candidate.id, failure_tags=candidate.failure_tags or [])


@router.post("/candidates/{candidate_id}/feedbacks", response_model=CandidateFeedbackResponse)
def create_feedback(
    candidate_id: str,
    request: CandidateFeedbackCreateRequest,
    db: Session = Depends(get_db),
) -> CandidateFeedbackResponse:
    candidate = get_candidate_or_404(db, candidate_id)

    if request.action not in VALID_FEEDBACK_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"유효하지 않은 action: {request.action}. 허용값: {sorted(VALID_FEEDBACK_ACTIONS)}",
        )
    invalid_tags = [t for t in request.failure_tags if t not in VALID_FAILURE_TYPES]
    if invalid_tags:
        raise HTTPException(
            status_code=422,
            detail=f"유효하지 않은 failure_type: {invalid_tags}. 허용값: {sorted(VALID_FAILURE_TYPES)}",
        )

    before_snapshot = {
        "status": candidate.status,
        "selected": candidate.selected,
        "total_score": float(candidate.total_score),
        "failure_tags": list(candidate.failure_tags or []),
    }

    feedback = CandidateFeedback(
        candidate_id=candidate.id,
        action=request.action,
        reason=request.reason,
        failure_tags=list(request.failure_tags),
        before_snapshot=before_snapshot,
        after_snapshot={},
        metadata_json=request.metadata,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return CandidateFeedbackResponse.from_model(feedback)


@router.get("/candidates/{candidate_id}/feedbacks", response_model=CandidateFeedbackListResponse)
def list_feedbacks(
    candidate_id: str,
    db: Session = Depends(get_db),
) -> CandidateFeedbackListResponse:
    _ = get_candidate_or_404(db, candidate_id)
    rows = list(
        db.scalars(
            select(CandidateFeedback)
            .where(CandidateFeedback.candidate_id == candidate_id)
            .order_by(CandidateFeedback.created_at.desc())
        )
    )
    total = db.scalar(
        select(func.count())
        .select_from(CandidateFeedback)
        .where(CandidateFeedback.candidate_id == candidate_id)
    ) or 0
    return CandidateFeedbackListResponse(
        items=[CandidateFeedbackResponse.from_model(fb) for fb in rows],
        total=total,
    )
