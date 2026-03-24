from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_export_or_404
from app.db.session import get_db
from app.schemas import ExportDetailResponse

router = APIRouter(tags=["exports"])


@router.get("/exports/{export_id}", response_model=ExportDetailResponse)
def get_export(export_id: str, db: Session = Depends(get_db)) -> ExportDetailResponse:
    return ExportDetailResponse.from_model(get_export_or_404(db, export_id))
