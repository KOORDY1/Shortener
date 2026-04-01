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


def _reorder_episode_candidates(
    db: Session,
    candidate: Candidate,
    new_rank: int,
) -> None:
    """같은 에피소드 내 후보들의 candidate_index를 일관되게 재정렬한다.

    new_rank 위치에 candidate를 끼워넣고, 나머지 후보의 인덱스를 shift한다.
    """
    siblings = list(
        db.scalars(
            select(Candidate)
            .where(Candidate.episode_id == candidate.episode_id)
            .order_by(Candidate.candidate_index.asc())
        )
    )

    # 목록에서 대상 후보 제거
    others = [c for c in siblings if c.id != candidate.id]

    # new_rank 위치(1-based)에 끼워넣기
    insert_idx = max(0, min(new_rank - 1, len(others)))
    others.insert(insert_idx, candidate)

    # 전체 인덱스 1-based 재할당
    for idx, c in enumerate(others):
        c.candidate_index = idx + 1
        db.add(c)


def _apply_feedback_action(
    db: Session,
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
        meta = dict(candidate.metadata_json or {})
        meta["edited"] = True
        candidate.metadata_json = meta

    elif action == FeedbackAction.REORDERED.value:
        if request.metadata.new_rank is not None:
            old_rank = candidate.candidate_index
            episode_count = db.scalar(
                select(func.count())
                .select_from(Candidate)
                .where(Candidate.episode_id == candidate.episode_id)
            ) or 1
            clamped_rank = max(1, min(request.metadata.new_rank, episode_count))
            _reorder_episode_candidates(db, candidate, clamped_rank)
            request.metadata.reorder_from = old_rank
            request.metadata.reorder_to = clamped_rank
            request.metadata.episode_candidate_count = episode_count
            meta = dict(candidate.metadata_json or {})
            meta["reordered"] = True
            candidate.metadata_json = meta

    # failure_tags 항상 동기화: []=clear, ["tag",...]=overwrite+dedupe
    candidate.failure_tags = list(dict.fromkeys(request.failure_tags))


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

    # action에 따라 Candidate 상태 변경 + failure_tags 동기화
    _apply_feedback_action(db, candidate, request.action, request)
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

    deduped_tags = list(dict.fromkeys(request.failure_tags))
    request.metadata.episode_selected_count = selected_count
    fb_metadata = {k: v for k, v in request.metadata.model_dump().items() if v is not None}

    # created_seq: 삽입 순서 보장 — max+1, unique 충돌 시 retry (최대 3회)
    from sqlalchemy.exc import IntegrityError as SAIntegrityError

    for _attempt in range(3):
        max_seq = db.scalar(
            select(func.coalesce(func.max(CandidateFeedback.created_seq), 0))
        ) or 0

        feedback = CandidateFeedback(
            candidate_id=candidate.id,
            created_seq=max_seq + 1,
            action=request.action,
            reason=request.reason,
            failure_tags=deduped_tags,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            metadata_json=fb_metadata,
        )
        db.add(feedback)
        try:
            db.flush()
            break
        except SAIntegrityError:
            db.rollback()
            # candidate 상태는 이미 변경됐으므로 다시 apply
            candidate = get_candidate_or_404(db, candidate_id)
            _apply_feedback_action(db, candidate, request.action, request)
            db.add(candidate)
            after_snapshot = _candidate_snapshot(candidate)
            feedback.after_snapshot = after_snapshot
    else:
        raise HTTPException(status_code=409, detail="피드백 생성 충돌 — 재시도 후에도 실패")

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
            .order_by(CandidateFeedback.created_seq.desc().nulls_last(), CandidateFeedback.created_at.desc())
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
