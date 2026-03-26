from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.db.models import Candidate
from app.schemas import ShortClipRenderRequest
from app.services.storage_service import episode_root

RENDER_EDITOR_META_KEY = "render_editor"


def candidate_files_root(candidate: Candidate) -> Path:
    return (episode_root(candidate.episode_id) / "candidates" / candidate.id).resolve()


def resolve_candidate_file(candidate: Candidate, raw_path: str | None) -> Path:
    if not raw_path:
        raise HTTPException(status_code=404, detail="요청한 파일이 없습니다.")
    path = Path(raw_path).expanduser().resolve()
    allowed = candidate_files_root(candidate)
    try:
        path.relative_to(allowed)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid clip path") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Clip file missing")
    return path


def editor_meta(candidate: Candidate) -> dict:
    return dict((candidate.metadata_json or {}).get(RENDER_EDITOR_META_KEY) or {})


def persist_editor_meta(candidate: Candidate, next_editor_meta: dict) -> None:
    metadata = dict(candidate.metadata_json or {})
    metadata[RENDER_EDITOR_META_KEY] = next_editor_meta
    candidate.metadata_json = metadata


def build_render_config_payload(
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
