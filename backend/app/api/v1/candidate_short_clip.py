from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.v1.candidate_common import (
    build_render_config_payload,
    editor_meta,
    persist_editor_meta,
    resolve_candidate_file,
)
from app.api.v1.deps import get_candidate_or_404
from app.db.models import JobType, TranscriptSegment
from app.db.session import get_db
from app.schemas import ShortClipRenderRequest, TriggerJobResponse
from app.services.jobs import create_job
from app.services.subtitle_exchange import delete_candidate_edited_ass, write_candidate_edited_ass
from app.tasks.pipelines import launch_short_clip_render

router = APIRouter(tags=["candidates"])


@router.get("/candidates/{candidate_id}/short-clip/video")
def stream_short_clip_video(candidate_id: str, db: Session = Depends(get_db)) -> FileResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    if not candidate.short_clip_path:
        raise HTTPException(
            status_code=404, detail="쇼츠 클립이 아직 없습니다. 먼저 렌더를 실행하세요."
        )
    path = resolve_candidate_file(candidate, candidate.short_clip_path)
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=path.name,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/candidates/{candidate_id}/short-clip/preview/video")
def stream_preview_clip_video(candidate_id: str, db: Session = Depends(get_db)) -> FileResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    preview_path = editor_meta(candidate).get("preview_clip_path")
    if not preview_path:
        raise HTTPException(status_code=404, detail="FFmpeg preview clip이 아직 없습니다.")
    path = resolve_candidate_file(candidate, preview_path)
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=path.name,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/candidates/{candidate_id}/short-clip", response_model=TriggerJobResponse)
def enqueue_short_clip_render(
    candidate_id: str,
    request: ShortClipRenderRequest,
    db: Session = Depends(get_db),
) -> TriggerJobResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    t0 = request.trim_start if request.trim_start is not None else candidate.start_time
    t1 = request.trim_end if request.trim_end is not None else candidate.end_time
    if t1 <= t0:
        raise HTTPException(status_code=400, detail="trim_end must be greater than trim_start")
    if request.use_imported_subtitles and not request.burn_subtitles:
        raise HTTPException(
            status_code=400,
            detail="가져온 자막으로 번인하려면 자막 번인을 켜 주세요.",
        )
    subtitle_source = request.subtitle_source if request.burn_subtitles else "none"
    use_imported_subtitles = request.use_imported_subtitles or subtitle_source == "file"
    use_edited_ass = request.use_edited_ass or subtitle_source == "edited-ass"
    if use_imported_subtitles and use_edited_ass:
        raise HTTPException(status_code=400, detail="subtitle source는 하나만 선택할 수 있습니다.")
    w, h = request.width, request.height
    if w < 480 or h < 480 or w > 3840 or h > 3840:
        raise HTTPException(status_code=400, detail="width/height out of allowed range")

    style_payload = request.subtitle_style.model_dump() if request.subtitle_style else {}
    subtitle_text_overrides: dict[str, str] = {}
    for override in request.subtitle_text_overrides or []:
        segment = db.get(TranscriptSegment, override.segment_id)
        if segment is None or segment.episode_id != candidate.episode_id:
            raise HTTPException(
                status_code=400,
                detail=f"subtitle_text_overrides: unknown segment_id {override.segment_id}",
            )
        subtitle_text_overrides[override.segment_id] = override.text

    next_editor_meta = editor_meta(candidate)
    if request.edited_ass is not None:
        content = request.edited_ass.strip()
        if content:
            stored = write_candidate_edited_ass(
                candidate.episode_id, candidate.id, request.edited_ass
            )
            next_editor_meta["edited_ass_path"] = str(stored.resolve())
        else:
            delete_candidate_edited_ass(candidate.episode_id, candidate.id)
            next_editor_meta.pop("edited_ass_path", None)

    if use_edited_ass and not next_editor_meta.get("edited_ass_path"):
        raise HTTPException(
            status_code=400, detail="ASS 원문이 비어 있습니다. 먼저 저장하거나 입력하세요."
        )

    render_config = build_render_config_payload(
        request,
        trim_start=t0,
        trim_end=t1,
        subtitle_style=style_payload,
        subtitle_text_overrides=subtitle_text_overrides,
        use_imported_subtitles=use_imported_subtitles,
        use_edited_ass=use_edited_ass,
    )
    if request.save_config:
        next_editor_meta["render_config"] = render_config
        if request.output_kind == "preview":
            next_editor_meta.pop("preview_clip_error", None)
        persist_editor_meta(candidate, next_editor_meta)
        db.add(candidate)
        db.commit()
        db.refresh(candidate)

    job = create_job(
        db,
        job_type=JobType.SHORT_CLIP_RENDER.value,
        episode_id=candidate.episode_id,
        candidate_id=candidate.id,
        payload={
            "trim_start": t0,
            "trim_end": t1,
            "burn_subtitles": request.burn_subtitles,
            "width": w,
            "height": h,
            "subtitle_style": style_payload,
            "subtitle_text_overrides": [
                {"segment_id": segment_id, "text": text}
                for segment_id, text in subtitle_text_overrides.items()
            ],
            "use_imported_subtitles": use_imported_subtitles,
            "use_edited_ass": use_edited_ass,
            "fit_mode": request.fit_mode,
            "quality_preset": request.quality_preset,
            "output_kind": request.output_kind,
        },
    )
    launch_short_clip_render(
        candidate_id=candidate.id,
        job_id=job.id,
        trim_start=t0,
        trim_end=t1,
        burn_subtitles=request.burn_subtitles,
        width=w,
        height=h,
        fit_mode=request.fit_mode,
        quality_preset=request.quality_preset,
        subtitle_style=style_payload,
        subtitle_text_overrides=subtitle_text_overrides,
        use_imported_subtitles=use_imported_subtitles,
        use_edited_ass=use_edited_ass,
        output_kind=request.output_kind,
    )
    db.refresh(job)
    return TriggerJobResponse(
        candidate_id=candidate.id,
        job_id=job.id,
        status=job.status,
        message="FFmpeg 렌더가 큐에 등록되었습니다.",
    )
