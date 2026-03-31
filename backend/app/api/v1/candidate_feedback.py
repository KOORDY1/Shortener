from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.v1.deps import get_candidate_or_404
from app.db.models import Candidate, CandidateFeedback, CandidateStatus, FeedbackAction
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


def _candidate_snapshot(candidate: Candidate) -> dict[str, str | bool | int | float | list[str]]:
    """Candidate의 현재 상태를 before/after snapshot dict로 생성."""
    return {
        "status": candidate.status,
        "selected": candidate.selected,
        "candidate_index": candidate.candidate_index,
        "total_score": float(candidate.total_score),
        "failure_tags": list(candidate.failure_tags or []),
    }


def _apply_feedback_action(
    candidate: Candidate,
    action: str,
    request: CandidateFeedbackCreateRequest,
) -> None:
    """feedback action에 따라 Candidate 상태를 실제로 변경한다."""
    if action == FeedbackAction.SELECTED.value:
        candidate.selected = True
        candidate.status = CandidateStatus.SELECTED.value

    elif action == FeedbackAction.REJECTED.value:
        candidate.selected = False
        candidate.status = CandidateStatus.REJECTED.value

    elif action == FeedbackAction.EDITED.value:
        # 실제 trim 수정은 강제하지 않지만, metadata에 edited 표시 기록
        meta = dict(candidate.metadata_json or {})
        meta["edited"] = True
        candidate.metadata_json = meta

    elif action == FeedbackAction.REORDERED.value:
        # request metadata에 new_rank가 있으면 candidate_index 업데이트
        new_rank = request.metadata.get("new_rank")
        if isinstance(new_rank, int) and 1 <= new_rank <= 14:
            candidate.candidate_index = new_rank
        meta = dict(candidate.metadata_json or {})
        meta["reordered"] = True
        candidate.metadata_json = meta


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

    # before snapshot
    before_snapshot = _candidate_snapshot(candidate)

    # action에 따라 Candidate 상태 변경
    _apply_feedback_action(candidate, request.action, request)
    db.add(candidate)

    # after snapshot (상태 변경 이후)
    after_snapshot = _candidate_snapshot(candidate)

    # 같은 에피소드 내 selected 후보 수 (정보 제공용)
    selected_count = db.scalar(
        select(func.count())
        .select_from(Candidate)
        .where(
            Candidate.episode_id == candidate.episode_id,
            Candidate.selected == True,  # noqa: E712
        )
    ) or 0

    feedback = CandidateFeedback(
        candidate_id=candidate.id,
        action=request.action,
        reason=request.reason,
        failure_tags=list(request.failure_tags),
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        metadata_json={
            **request.metadata,
            "episode_selected_count": selected_count,
        },
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
