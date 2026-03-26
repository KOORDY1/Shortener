from __future__ import annotations

import json
import shutil
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Candidate,
    Episode,
    Export,
    ExportStatus,
    Job,
    JobType,
    ScriptDraft,
    VideoDraft,
    VideoDraftStatus,
)
from app.services.jobs import create_job, mark_job_running, mark_job_succeeded
from app.services.video_template_renderer import (
    build_default_video_render_config,
    render_video_draft_assets,
)


def next_video_draft_version(db: Session, candidate_id: str) -> int:
    current = db.scalar(
        select(func.coalesce(func.max(VideoDraft.version_no), 0)).where(
            VideoDraft.candidate_id == candidate_id
        )
    )
    return int(current or 0) + 1


def next_export_version(db: Session, video_draft_id: str) -> int:
    current = db.scalar(
        select(func.coalesce(func.count(Export.id), 0)).where(Export.video_draft_id == video_draft_id)
    )
    return int(current or 0) + 1


def _next_render_revision(video_draft: VideoDraft) -> int:
    raw = (video_draft.metadata_json or {}).get("render_revision")
    try:
        return int(raw) + 1
    except (TypeError, ValueError):
        return 1


def create_video_draft(
    db: Session,
    *,
    candidate: Candidate,
    script_draft: ScriptDraft,
    template_type: str,
    tts_voice_key: str | None,
    burned_caption: bool,
    render_config: dict | None = None,
) -> VideoDraft:
    version_no = next_video_draft_version(db, candidate.id)
    vd = VideoDraft(
        candidate_id=candidate.id,
        script_draft_id=script_draft.id,
        version_no=version_no,
        status=VideoDraftStatus.CREATED.value,
        template_type=template_type,
        tts_voice_key=tts_voice_key,
        burned_caption=burned_caption,
        timeline_json={},
        render_config_json=render_config or {},
        metadata_json={},
    )
    db.add(vd)
    db.commit()
    db.refresh(vd)
    return render_video_draft(db, vd)


def render_video_draft(db: Session, video_draft: VideoDraft) -> VideoDraft:
    if video_draft.status == VideoDraftStatus.REJECTED.value:
        raise ValueError("rejected drafts cannot be rerendered")

    candidate = db.get(Candidate, video_draft.candidate_id)
    script_draft = db.get(ScriptDraft, video_draft.script_draft_id)
    if candidate is None or script_draft is None:
        raise ValueError("Candidate or script draft not found")
    render_revision = _next_render_revision(video_draft)
    from app.services.storage_service import episode_root

    output_dir = episode_root(candidate.episode_id) / "candidates" / candidate.id / "video_drafts" / str(
        video_draft.version_no
    )

    episode = db.get(Episode, candidate.episode_id)
    if episode is None:
        raise ValueError("Episode not found")
    default_render_config = build_default_video_render_config(
        episode=episode,
        candidate=candidate,
        script_draft=script_draft,
        template_type=video_draft.template_type,
        burned_caption=video_draft.burned_caption,
        tts_voice_key=video_draft.tts_voice_key,
    )
    if not video_draft.render_config_json:
        video_draft.render_config_json = default_render_config

    result = render_video_draft_assets(
        db,
        video_draft=video_draft,
        render_revision=render_revision,
        output_dir=output_dir,
        target_stem="draft",
    )
    video_draft.status = VideoDraftStatus.READY.value
    video_draft.draft_video_path = result["video_path"]
    video_draft.subtitle_path = result["subtitle_path"]
    video_draft.thumbnail_path = result["thumbnail_path"]
    video_draft.render_config_json = result["render_config"]
    video_draft.timeline_json = result["timeline_json"]
    video_draft.metadata_json = {
        **(video_draft.metadata_json or {}),
        **result["metadata"],
        "render_revision": render_revision,
    }
    db.add(video_draft)
    db.commit()
    db.refresh(video_draft)
    return video_draft


def create_export(
    db: Session,
    *,
    video_draft: VideoDraft,
    export_preset: str,
    include_srt: bool,
    include_script_txt: bool,
    include_metadata_json: bool,
) -> Export:
    candidate = db.get(Candidate, video_draft.candidate_id)
    if candidate is None:
        raise ValueError("Candidate not found for video draft")
    if not video_draft.draft_video_path:
        raise ValueError("Video draft has no rendered video")
    export_version = next_export_version(db, video_draft.id)
    export_dir = (
        Path(video_draft.draft_video_path).resolve().parent.parent / "exports" / f"export_{export_version}"
    )
    export_dir.mkdir(parents=True, exist_ok=True)

    export_video_path = export_dir / f"final_export_v{export_version}.mp4"
    shutil.copy2(video_draft.draft_video_path, export_video_path)

    export_subtitle_path = None
    if include_srt and video_draft.subtitle_path:
        export_subtitle_path = export_dir / f"final_export_v{export_version}.srt"
        shutil.copy2(video_draft.subtitle_path, export_subtitle_path)

    export_script_path = None
    if include_script_txt:
        script = db.get(ScriptDraft, video_draft.script_draft_id)
        export_script_path = export_dir / f"script_v{export_version}.txt"
        export_script_path.write_text(
            (script.full_script_text if script else "").strip(),
            encoding="utf-8",
        )

    export_metadata_path = None
    metadata_payload = {
        "export_version": export_version,
        "video_draft_id": video_draft.id,
        "video_draft_metadata": video_draft.metadata_json or {},
        "render_config": video_draft.render_config_json or {},
        "timeline_json": video_draft.timeline_json or {},
    }
    if include_metadata_json:
        export_metadata_path = export_dir / f"meta_v{export_version}.json"
        export_metadata_path.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    exp = Export(
        video_draft_id=video_draft.id,
        status=ExportStatus.READY.value,
        export_preset=export_preset,
        export_video_path=str(export_video_path.resolve()),
        export_subtitle_path=str(export_subtitle_path.resolve()) if export_subtitle_path else None,
        export_script_path=str(export_script_path.resolve()) if export_script_path else None,
        export_metadata_path=str(export_metadata_path.resolve()) if export_metadata_path else None,
        file_size_bytes=export_video_path.stat().st_size if export_video_path.is_file() else None,
        metadata_json=metadata_payload,
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def run_rerender(db: Session, video_draft: VideoDraft) -> tuple[Job, VideoDraft]:
    if video_draft.status == VideoDraftStatus.REJECTED.value:
        raise ValueError("rejected drafts cannot be rerendered")

    candidate = db.get(Candidate, video_draft.candidate_id)
    if candidate is None:
        raise ValueError("Candidate not found for video draft")

    job = create_job(
        db,
        job_type=JobType.VIDEO_DRAFT_RENDER.value,
        episode_id=candidate.episode_id,
        candidate_id=candidate.id,
        payload={"video_draft_id": video_draft.id, "render_type": "video_draft"},
    )
    mark_job_running(db, job, step="render_video_draft", progress_percent=50)
    updated = render_video_draft(db, video_draft)
    mark_job_succeeded(
        db,
        job,
        payload={
            "video_draft_id": updated.id,
            "draft_video_path": updated.draft_video_path,
            "render_revision": (updated.metadata_json or {}).get("render_revision"),
        },
    )
    return job, updated
