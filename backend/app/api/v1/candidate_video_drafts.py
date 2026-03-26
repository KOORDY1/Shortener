from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_candidate_or_404, get_script_draft_or_404
from app.db.models import VideoDraft
from app.db.session import get_db
from app.schemas import TriggerJobResponse, VideoDraftCreateRequest, VideoDraftListResponse, VideoDraftSummary
from app.services.video_draft_service import create_mock_video_draft

router = APIRouter(tags=["candidates"])


@router.get("/candidates/{candidate_id}/video-drafts", response_model=VideoDraftListResponse)
def list_candidate_video_drafts(
    candidate_id: str, db: Session = Depends(get_db)
) -> VideoDraftListResponse:
    get_candidate_or_404(db, candidate_id)
    items = list(
        db.scalars(
            select(VideoDraft)
            .where(VideoDraft.candidate_id == candidate_id)
            .order_by(VideoDraft.version_no.desc())
        )
    )
    return VideoDraftListResponse(
        items=[VideoDraftSummary.from_model(item) for item in items], total=len(items)
    )


@router.post("/candidates/{candidate_id}/video-drafts", response_model=TriggerJobResponse)
def create_candidate_video_draft(
    candidate_id: str,
    request: VideoDraftCreateRequest,
    db: Session = Depends(get_db),
) -> TriggerJobResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    script_draft = get_script_draft_or_404(db, request.script_draft_id)
    if script_draft.candidate_id != candidate.id:
        raise HTTPException(
            status_code=400, detail="script_draft does not belong to this candidate"
        )

    video_draft = create_mock_video_draft(
        db,
        candidate=candidate,
        script_draft=script_draft,
        template_type=request.template_type,
        tts_voice_key=request.tts_voice_key,
        burned_caption=request.burned_caption,
    )
    return TriggerJobResponse(
        candidate_id=candidate.id,
        video_draft_id=video_draft.id,
        status=video_draft.status,
        message="Mock video draft created (no render worker)",
    )
