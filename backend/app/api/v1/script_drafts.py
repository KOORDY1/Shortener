from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_script_draft_or_404
from app.db.models import ScriptDraft
from app.db.session import get_db
from app.schemas import ScriptDraftResponse, ScriptDraftUpdateRequest

router = APIRouter(tags=["script-drafts"])


@router.patch("/script-drafts/{script_draft_id}", response_model=ScriptDraftResponse)
def update_script_draft(
    script_draft_id: str,
    request: ScriptDraftUpdateRequest,
    db: Session = Depends(get_db),
) -> ScriptDraftResponse:
    draft = get_script_draft_or_404(db, script_draft_id)

    if request.hook_text is not None:
        draft.hook_text = request.hook_text
    if request.body_text is not None:
        draft.body_text = request.body_text
    if request.cta_text is not None:
        draft.cta_text = request.cta_text
    if request.title_options is not None:
        draft.title_options = request.title_options

    draft.full_script_text = " ".join(
        part for part in [draft.hook_text, draft.body_text, draft.cta_text] if part
    )
    draft.estimated_duration_seconds = round(max(15.0, len(draft.full_script_text) / 12), 2)
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return ScriptDraftResponse.from_model(draft)


@router.post("/script-drafts/{script_draft_id}/select", response_model=ScriptDraftResponse)
def select_script_draft(script_draft_id: str, db: Session = Depends(get_db)) -> ScriptDraftResponse:
    draft = get_script_draft_or_404(db, script_draft_id)

    sibling_drafts = list(
        db.scalars(select(ScriptDraft).where(ScriptDraft.candidate_id == draft.candidate_id))
    )
    for item in sibling_drafts:
        item.is_selected = item.id == draft.id
        db.add(item)

    db.commit()
    db.refresh(draft)
    return ScriptDraftResponse.from_model(draft)
