from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.api.v1.candidate_common import editor_meta, persist_editor_meta
from app.api.v1.deps import get_candidate_or_404
from app.db.session import get_db
from app.schemas import EditedAssPayload, EditedAssResponse
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

router = APIRouter(tags=["candidates"])


@router.get("/candidates/{candidate_id}/subtitles/webvtt")
def export_candidate_webvtt(
    candidate_id: str,
    trim_start: float | None = None,
    trim_end: float | None = None,
    db: Session = Depends(get_db),
) -> Response:
    candidate = get_candidate_or_404(db, candidate_id)
    render_config = editor_meta(candidate).get("render_config") or {}
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
    segments = transcript_segments_for_clip(db, candidate.episode_id, t0, t1)
    overrides = {
        str(item.get("segment_id")): str(item.get("text", ""))
        for item in (render_config.get("subtitle_text_overrides") or [])
        if isinstance(item, dict) and item.get("segment_id")
    }
    body = build_webvtt_absolute_for_range(segments, t0, t1, overrides)
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
    segments = transcript_segments_for_clip(db, candidate.episode_id, t0, t1)
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
    body = build_ass_for_clip(segments, t0, t1, style, None)
    filename = f"clip_subs_{candidate_id[:8]}.ass"
    return Response(
        content=body.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
    next_editor_meta = editor_meta(candidate)
    if content:
        stored = write_candidate_edited_ass(candidate.episode_id, candidate.id, request.content)
        next_editor_meta["edited_ass_path"] = str(stored.resolve())
    else:
        delete_candidate_edited_ass(candidate.episode_id, candidate.id)
        next_editor_meta.pop("edited_ass_path", None)
    persist_editor_meta(candidate, next_editor_meta)
    db.add(candidate)
    db.commit()
    return EditedAssResponse(content=request.content, has_content=bool(content))
