from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_candidate_or_404
from app.db.models import CandidateFeedback
from app.db.session import get_db
from app.schemas import CandidateDetailResponse, CandidateFeedbackSummary
from app.services.analysis_service import candidate_segments, candidate_shots

router = APIRouter(tags=["candidates"])


def _build_feedback_summary(db: Session, candidate_id: str) -> CandidateFeedbackSummary:
    """후보의 피드백 요약(건수, 최신 액션/시각)을 DB에서 조회한다."""
    feedbacks = list(
        db.scalars(
            select(CandidateFeedback)
            .where(CandidateFeedback.candidate_id == candidate_id)
            .order_by(CandidateFeedback.created_at.desc())
            .limit(1)
        )
    )
    from sqlalchemy import func

    count = db.scalar(
        select(func.count())
        .select_from(CandidateFeedback)
        .where(CandidateFeedback.candidate_id == candidate_id)
    ) or 0

    if feedbacks:
        latest = feedbacks[0]
        return CandidateFeedbackSummary(
            feedback_count=count,
            latest_feedback_action=latest.action,
            latest_feedback_at=latest.created_at,
        )
    return CandidateFeedbackSummary(feedback_count=count)


@router.get("/candidates/{candidate_id}", response_model=CandidateDetailResponse)
def get_candidate(candidate_id: str, db: Session = Depends(get_db)) -> CandidateDetailResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    segments = candidate_segments(db, candidate)
    shots = candidate_shots(db, candidate)
    fb_summary = _build_feedback_summary(db, candidate_id)
    return CandidateDetailResponse.from_model(candidate, segments, shots, fb_summary)
