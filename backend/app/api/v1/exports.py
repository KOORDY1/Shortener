from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.v1.deps import get_export_or_404
from app.db.session import get_db
from app.schemas import ExportDetailResponse

router = APIRouter(tags=["exports"])


def _resolve_file(path_str: str | None) -> Path:
    if not path_str:
        raise HTTPException(status_code=404, detail="file not found")
    path = Path(path_str).expanduser().resolve()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return path


@router.get("/exports/{export_id}", response_model=ExportDetailResponse)
def get_export(export_id: str, db: Session = Depends(get_db)) -> ExportDetailResponse:
    return ExportDetailResponse.from_model(get_export_or_404(db, export_id))


@router.get("/exports/{export_id}/video")
def stream_export_video(export_id: str, db: Session = Depends(get_db)) -> FileResponse:
    export = get_export_or_404(db, export_id)
    path = _resolve_file(export.export_video_path)
    return FileResponse(path, media_type="video/mp4", filename=path.name, headers={"Cache-Control": "no-store"})


@router.get("/exports/{export_id}/subtitle")
def download_export_subtitle(export_id: str, db: Session = Depends(get_db)) -> FileResponse:
    export = get_export_or_404(db, export_id)
    path = _resolve_file(export.export_subtitle_path)
    return FileResponse(path, media_type="text/plain; charset=utf-8", filename=path.name, headers={"Cache-Control": "no-store"})


@router.get("/exports/{export_id}/script")
def download_export_script(export_id: str, db: Session = Depends(get_db)) -> FileResponse:
    export = get_export_or_404(db, export_id)
    path = _resolve_file(export.export_script_path)
    return FileResponse(path, media_type="text/plain; charset=utf-8", filename=path.name, headers={"Cache-Control": "no-store"})


@router.get("/exports/{export_id}/metadata")
def download_export_metadata(export_id: str, db: Session = Depends(get_db)) -> FileResponse:
    export = get_export_or_404(db, export_id)
    path = _resolve_file(export.export_metadata_path)
    return FileResponse(path, media_type="application/json", filename=path.name, headers={"Cache-Control": "no-store"})
