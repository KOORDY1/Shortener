from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.deps import get_candidate_or_404, get_script_draft_or_404
from app.db.models import (
    Candidate,
    CandidateStatus,
    JobType,
    ScriptDraft,
    TranscriptSegment,
    VideoDraft,
)
from app.db.session import get_db
from app.schemas import (
    CandidateDetailResponse,
    CandidateRejectRequest,
    CandidateSelectionRequest,
    EditedAssPayload,
    EditedAssResponse,
    ScriptDraftCreateRequest,
    ScriptDraftListResponse,
    ScriptDraftResponse,
    ShortClipRenderRequest,
    TriggerJobResponse,
    VideoDraftCreateRequest,
    VideoDraftListResponse,
    VideoDraftSummary,
)
from app.services.analysis_service import candidate_segments, candidate_shots
from app.services.jobs import create_job
from app.services.storage_service import episode_root
from app.services.subtitle_exchange import (
    IMPORTED_ASS,
    IMPORTED_VTT,
    build_ass_for_clip,
    build_webvtt_absolute_for_range,
    candidate_subtitle_dir,
    delete_candidate_edited_ass,
    read_candidate_edited_ass,
    transcript_segments_for_clip,
    write_candidate_edited_ass,
)
from app.services.video_draft_service import create_mock_video_draft
from app.tasks.pipelines import launch_script_generation, launch_short_clip_render

router = APIRouter(tags=["candidates"])

RENDER_EDITOR_META_KEY = "render_editor"


def _candidate_files_root(candidate: Candidate) -> Path:
    return (episode_root(candidate.episode_id) / "candidates" / candidate.id).resolve()


def _resolve_candidate_file(candidate: Candidate, raw_path: str | None) -> Path:
    if not raw_path:
        raise HTTPException(status_code=404, detail="요청한 파일이 없습니다.")
    path = Path(raw_path).expanduser().resolve()
    allowed = _candidate_files_root(candidate)
    try:
        path.relative_to(allowed)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid clip path") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Clip file missing")
    return path


def _editor_meta(candidate: Candidate) -> dict:
    return dict((candidate.metadata_json or {}).get(RENDER_EDITOR_META_KEY) or {})


def _persist_editor_meta(candidate: Candidate, editor_meta: dict) -> None:
    metadata = dict(candidate.metadata_json or {})
    metadata[RENDER_EDITOR_META_KEY] = editor_meta
    candidate.metadata_json = metadata


def _render_config_payload(
    request: ShortClipRenderRequest,
    *,
    trim_start: float,
    trim_end: float,
    subtitle_style: dict[str, object],
    subtitle_text_overrides: dict[str, str],
    use_imported_subtitles: bool,
    use_edited_ass: bool,
) -> dict[str, object]:
    subtitle_source = request.subtitle_source
    if not request.burn_subtitles:
        subtitle_source = "none"
    return {
        "trim_start": trim_start,
        "trim_end": trim_end,
        "burn_subtitles": request.burn_subtitles,
        "subtitle_source": subtitle_source,
        "aspect_ratio": request.aspect_ratio,
        "fit_mode": request.fit_mode,
        "quality_preset": request.quality_preset,
        "resolution_preset": request.resolution_preset,
        "width": request.width,
        "height": request.height,
        "subtitle_style": subtitle_style,
        "subtitle_text_overrides": [
            {"segment_id": segment_id, "text": text}
            for segment_id, text in subtitle_text_overrides.items()
        ],
        "use_imported_subtitles": use_imported_subtitles,
        "use_edited_ass": use_edited_ass,
    }


@router.get("/candidates/{candidate_id}/short-clip/video")
def stream_short_clip_video(candidate_id: str, db: Session = Depends(get_db)) -> FileResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    if not candidate.short_clip_path:
        raise HTTPException(
            status_code=404, detail="쇼츠 클립이 아직 없습니다. 먼저 렌더를 실행하세요."
        )
    path = _resolve_candidate_file(candidate, candidate.short_clip_path)
    return FileResponse(path, media_type="video/mp4", filename="short_clip.mp4")


@router.get("/candidates/{candidate_id}/short-clip/preview/video")
def stream_preview_clip_video(candidate_id: str, db: Session = Depends(get_db)) -> FileResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    preview_path = _editor_meta(candidate).get("preview_clip_path")
    if not preview_path:
        raise HTTPException(status_code=404, detail="FFmpeg preview clip이 아직 없습니다.")
    path = _resolve_candidate_file(candidate, preview_path)
    return FileResponse(path, media_type="video/mp4", filename="preview_clip.mp4")


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
    ov_dict: dict[str, str] = {}
    for o in request.subtitle_text_overrides or []:
        seg = db.get(TranscriptSegment, o.segment_id)
        if seg is None or seg.episode_id != candidate.episode_id:
            raise HTTPException(
                status_code=400,
                detail=f"subtitle_text_overrides: unknown segment_id {o.segment_id}",
            )
        ov_dict[o.segment_id] = o.text

    editor_meta = _editor_meta(candidate)
    if request.edited_ass is not None:
        content = request.edited_ass.strip()
        if content:
            stored = write_candidate_edited_ass(
                candidate.episode_id, candidate.id, request.edited_ass
            )
            editor_meta["edited_ass_path"] = str(stored.resolve())
        else:
            delete_candidate_edited_ass(candidate.episode_id, candidate.id)
            editor_meta.pop("edited_ass_path", None)

    if use_edited_ass and not editor_meta.get("edited_ass_path"):
        raise HTTPException(
            status_code=400, detail="ASS 원문이 비어 있습니다. 먼저 저장하거나 입력하세요."
        )

    render_config = _render_config_payload(
        request,
        trim_start=t0,
        trim_end=t1,
        subtitle_style=style_payload,
        subtitle_text_overrides=ov_dict,
        use_imported_subtitles=use_imported_subtitles,
        use_edited_ass=use_edited_ass,
    )
    if request.save_config:
        editor_meta["render_config"] = render_config
        if request.output_kind == "preview":
            editor_meta.pop("preview_clip_error", None)
        _persist_editor_meta(candidate, editor_meta)
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
            "subtitle_text_overrides": [{"segment_id": k, "text": v} for k, v in ov_dict.items()],
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
        subtitle_text_overrides=ov_dict,
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


@router.get("/candidates/{candidate_id}/subtitles/webvtt")
def export_candidate_webvtt(
    candidate_id: str,
    trim_start: float | None = None,
    trim_end: float | None = None,
    db: Session = Depends(get_db),
) -> Response:
    candidate = get_candidate_or_404(db, candidate_id)
    render_config = _editor_meta(candidate).get("render_config") or {}
    t0 = (
        trim_start
        if trim_start is not None
        else render_config.get("trim_start", candidate.start_time)
    )
    t1 = trim_end if trim_end is not None else render_config.get("trim_end", candidate.end_time)
    if t1 <= t0:
        raise HTTPException(status_code=400, detail="trim_end must be greater than trim_start")
    subtitle_source = render_config.get("subtitle_source")
    imported = candidate_subtitle_dir(candidate.episode_id, candidate.id) / IMPORTED_VTT
    if subtitle_source == "file" and imported.is_file():
        return FileResponse(
            imported,
            media_type="text/vtt; charset=utf-8",
            filename="imported_subs.vtt",
            headers={"Cache-Control": "no-store"},
        )
    if subtitle_source == "edited-ass":
        return Response(
            content="WEBVTT\n\n",
            media_type="text/vtt; charset=utf-8",
            headers={"Cache-Control": "no-store"},
        )
    segs = transcript_segments_for_clip(db, candidate.episode_id, t0, t1)
    overrides = {
        str(item.get("segment_id")): str(item.get("text", ""))
        for item in (render_config.get("subtitle_text_overrides") or [])
        if isinstance(item, dict) and item.get("segment_id")
    }
    body = build_webvtt_absolute_for_range(segs, t0, t1, overrides)
    return Response(
        content=body,
        media_type="text/vtt; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/candidates/{candidate_id}/subtitles/ass")
def export_candidate_ass(
    candidate_id: str,
    trim_start: float | None = None,
    trim_end: float | None = None,
    font_size: int = 28,
    alignment: int = 2,
    margin_v: int = 52,
    outline: int = 2,
    font_family: str = "Noto Sans CJK KR",
    primary_color: str = "#FFFFFF",
    outline_color: str = "#000000",
    shadow: int = 0,
    background_box: bool = False,
    bold: bool = False,
    db: Session = Depends(get_db),
) -> Response:
    candidate = get_candidate_or_404(db, candidate_id)
    t0 = trim_start if trim_start is not None else candidate.start_time
    t1 = trim_end if trim_end is not None else candidate.end_time
    if t1 <= t0:
        raise HTTPException(status_code=400, detail="trim_end must be greater than trim_start")
    segs = transcript_segments_for_clip(db, candidate.episode_id, t0, t1)
    style = {
        "font_family": font_family,
        "font_size": font_size,
        "alignment": alignment,
        "margin_v": margin_v,
        "outline": outline,
        "primary_color": primary_color,
        "outline_color": outline_color,
        "shadow": shadow,
        "background_box": background_box,
        "bold": bold,
    }
    body = build_ass_for_clip(segs, t0, t1, style, None)
    fn = f"clip_subs_{candidate_id[:8]}.ass"
    return Response(
        content=body.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{fn}"'},
    )


@router.post("/candidates/{candidate_id}/subtitles/import")
async def import_candidate_subtitles(
    candidate_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, str | bool]:
    candidate = get_candidate_or_404(db, candidate_id)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".ass", ".vtt"):
        raise HTTPException(status_code=400, detail="지원 형식: .ass 또는 .vtt")
    out_dir = candidate_subtitle_dir(candidate.episode_id, candidate.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = IMPORTED_ASS if suffix == ".ass" else IMPORTED_VTT
    other = IMPORTED_VTT if suffix == ".ass" else IMPORTED_ASS
    (out_dir / other).unlink(missing_ok=True)
    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(status_code=400, detail="파일 크기는 5MB 이하여야 합니다.")
    (out_dir / name).write_bytes(data)
    return {"ok": True, "stored_as": name}


@router.get("/candidates/{candidate_id}/subtitles/edited-ass", response_model=EditedAssResponse)
def get_candidate_edited_ass(candidate_id: str, db: Session = Depends(get_db)) -> EditedAssResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    content = read_candidate_edited_ass(candidate.episode_id, candidate.id) or ""
    return EditedAssResponse(content=content, has_content=bool(content.strip()))


@router.put("/candidates/{candidate_id}/subtitles/edited-ass", response_model=EditedAssResponse)
def save_candidate_edited_ass(
    candidate_id: str,
    request: EditedAssPayload,
    db: Session = Depends(get_db),
) -> EditedAssResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    content = request.content.strip()
    editor_meta = _editor_meta(candidate)
    if content:
        stored = write_candidate_edited_ass(candidate.episode_id, candidate.id, request.content)
        editor_meta["edited_ass_path"] = str(stored.resolve())
    else:
        delete_candidate_edited_ass(candidate.episode_id, candidate.id)
        editor_meta.pop("edited_ass_path", None)
    _persist_editor_meta(candidate, editor_meta)
    db.add(candidate)
    db.commit()
    return EditedAssResponse(content=request.content, has_content=bool(content))


@router.get("/candidates/{candidate_id}", response_model=CandidateDetailResponse)
def get_candidate(candidate_id: str, db: Session = Depends(get_db)) -> CandidateDetailResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    segments = candidate_segments(db, candidate)
    shots = candidate_shots(db, candidate)
    return CandidateDetailResponse.from_model(candidate, segments, shots)


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
    meta = dict(candidate.metadata_json or {})
    rejection_reasons = list(meta.get("rejection_reasons") or [])
    rejection_reasons.append(request.reason)
    meta["rejection_reasons"] = rejection_reasons
    candidate.metadata_json = meta
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return CandidateDetailResponse.from_model(
        candidate,
        candidate_segments(db, candidate),
        candidate_shots(db, candidate),
    )


@router.post("/candidates/{candidate_id}/script-drafts", response_model=TriggerJobResponse)
def create_script_drafts(
    candidate_id: str,
    request: ScriptDraftCreateRequest,
    db: Session = Depends(get_db),
) -> TriggerJobResponse:
    candidate = get_candidate_or_404(db, candidate_id)
    job = create_job(
        db,
        job_type=JobType.SCRIPT_GENERATION.value,
        episode_id=candidate.episode_id,
        candidate_id=candidate.id,
        payload=request.model_dump(),
    )
    launch_script_generation(
        candidate_id=candidate.id,
        job_id=job.id,
        language=request.language,
        versions=request.versions,
        tone=request.tone,
        channel_style=request.channel_style,
        force_regenerate=request.force_regenerate,
    )
    db.refresh(job)
    return TriggerJobResponse(candidate_id=candidate.id, job_id=job.id, status=job.status)


@router.get("/candidates/{candidate_id}/script-drafts", response_model=ScriptDraftListResponse)
def list_script_drafts(candidate_id: str, db: Session = Depends(get_db)) -> ScriptDraftListResponse:
    get_candidate_or_404(db, candidate_id)
    items = list(
        db.scalars(
            select(ScriptDraft)
            .where(ScriptDraft.candidate_id == candidate_id)
            .order_by(ScriptDraft.version_no.asc())
        )
    )
    return ScriptDraftListResponse(items=[ScriptDraftResponse.from_model(item) for item in items])


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

    vd = create_mock_video_draft(
        db,
        candidate=candidate,
        script_draft=script_draft,
        template_type=request.template_type,
        tts_voice_key=request.tts_voice_key,
        burned_caption=request.burned_caption,
    )
    return TriggerJobResponse(
        candidate_id=candidate.id,
        video_draft_id=vd.id,
        status=vd.status,
        message="Mock video draft created (no render worker)",
    )
