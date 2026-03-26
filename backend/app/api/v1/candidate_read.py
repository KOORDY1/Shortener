from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_candidate_or_404
from app.db.session import get_db
from app.schemas import CandidateDetailResponse
from app.services.analysis_service import candidate_segments, candidate_shots

router = APIRouter(tags=["candidates"])


@router.get("/candidates/{candidate_id}", response_model=CandidateDetailResponse)
def get_candidate(candidate_id: str, db: Session = Depends(get_db)) -> CandidateDetailResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    segments = candidate_segments(db, candidate)
    shots = candidate_shots(db, candidate)
    return CandidateDetailResponse.from_model(candidate, segments, shots)
