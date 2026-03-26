from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.v1.deps import get_video_draft_or_404
from app.db.models import VideoDraftStatus
from app.db.session import get_db
from app.schemas import (
    ExportCreateRequest,
    TriggerJobResponse,
    VideoDraftDetailResponse,
    VideoDraftPatchRequest,
    VideoDraftRejectRequest,
)
from app.services.video_draft_service import create_mock_export, run_mock_rerender

router = APIRouter(tags=["video-drafts"])


@router.get("/video-drafts/{video_draft_id}", response_model=VideoDraftDetailResponse)
def get_video_draft(video_draft_id: str, db: Session = Depends(get_db)) -> VideoDraftDetailResponse:
    return VideoDraftDetailResponse.from_model(get_video_draft_or_404(db, video_draft_id))


@router.patch("/video-drafts/{video_draft_id}", response_model=VideoDraftDetailResponse)
def patch_video_draft(
    video_draft_id: str,
    request: VideoDraftPatchRequest,
    db: Session = Depends(get_db),
) -> VideoDraftDetailResponse:
    vd = get_video_draft_or_404(db, video_draft_id)
    if request.operator_notes is not None:
        vd.operator_notes = request.operator_notes
    if request.timeline_json is not None:
        vd.timeline_json = request.timeline_json
    if request.render_config is not None:
        vd.render_config_json = request.render_config
    db.add(vd)
    db.commit()
    db.refresh(vd)
    return VideoDraftDetailResponse.from_model(vd)


@router.post("/video-drafts/{video_draft_id}/rerender", response_model=TriggerJobResponse)
def rerender_video_draft(video_draft_id: str, db: Session = Depends(get_db)) -> TriggerJobResponse:
    vd = get_video_draft_or_404(db, video_draft_id)
    try:
        job, updated = run_mock_rerender(db, vd)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return TriggerJobResponse(
        candidate_id=updated.candidate_id,
        job_id=job.id,
        video_draft_id=updated.id,
        status=job.status,
        message="Mock rerender completed (no FFmpeg worker)",
    )


@router.post("/video-drafts/{video_draft_id}/approve", response_model=VideoDraftDetailResponse)
def approve_video_draft(
    video_draft_id: str, db: Session = Depends(get_db)
) -> VideoDraftDetailResponse:
    vd = get_video_draft_or_404(db, video_draft_id)
    vd.status = VideoDraftStatus.APPROVED.value
    db.add(vd)
    db.commit()
    db.refresh(vd)
    return VideoDraftDetailResponse.from_model(vd)


@router.post("/video-drafts/{video_draft_id}/reject", response_model=VideoDraftDetailResponse)
def reject_video_draft(
    video_draft_id: str,
    request: VideoDraftRejectRequest,
    db: Session = Depends(get_db),
) -> VideoDraftDetailResponse:
    vd = get_video_draft_or_404(db, video_draft_id)
    vd.status = VideoDraftStatus.REJECTED.value
    if request.reason:
        prev = (vd.operator_notes or "").strip()
        note = f"[reject] {request.reason.strip()}"
        vd.operator_notes = f"{prev}\n{note}" if prev else note
    db.add(vd)
    db.commit()
    db.refresh(vd)
    return VideoDraftDetailResponse.from_model(vd)


@router.post("/video-drafts/{video_draft_id}/exports", response_model=TriggerJobResponse)
def create_video_draft_export(
    video_draft_id: str,
    request: ExportCreateRequest,
    db: Session = Depends(get_db),
) -> TriggerJobResponse:
    vd = get_video_draft_or_404(db, video_draft_id)
    exp = create_mock_export(
        db,
        video_draft=vd,
        export_preset=request.export_preset,
        include_srt=request.include_srt,
        include_script_txt=request.include_script_txt,
        include_metadata_json=request.include_metadata_json,
    )
    return TriggerJobResponse(
        candidate_id=vd.candidate_id,
        video_draft_id=vd.id,
        export_id=exp.id,
        status=exp.status,
        message="Mock export created",
    )
