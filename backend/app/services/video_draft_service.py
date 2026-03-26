from __future__ import annotations

import json
import shutil
import subprocess
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
from app.services.jobs import create_job
from app.services.video_template_renderer import (
    build_default_video_render_config,
    render_video_draft_assets,
)

EXPORT_PRESETS: dict[str, dict[str, object]] = {
    "shorts_default": {
        "width": 1080,
        "height": 1920,
        "preset": "fast",
        "crf": "23",
        "watermark": None,
    },
    "review_lowres": {
        "width": 720,
        "height": 1280,
        "preset": "veryfast",
        "crf": "30",
        "watermark": "INTERNAL REVIEW",
    },
    "archive_master": {
        "width": None,
        "height": None,
        "preset": "medium",
        "crf": "18",
        "watermark": None,
    },
}


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


def _resolve_export_profile(export_preset: str) -> dict[str, object]:
    return dict(EXPORT_PRESETS.get(export_preset, EXPORT_PRESETS["shorts_default"]))


def _render_export_video(
    *,
    source_path: Path,
    output_path: Path,
    export_preset: str,
) -> None:
    profile = _resolve_export_profile(export_preset)
    width = profile.get("width")
    height = profile.get("height")
    watermark = profile.get("watermark")
    filters: list[str] = []
    if width and height:
        filters.append(
            f"scale={int(width)}:{int(height)}:force_original_aspect_ratio=decrease,pad={int(width)}:{int(height)}:(ow-iw)/2:(oh-ih)/2"
        )
    if watermark:
        filters.append(
            "drawtext=text='INTERNAL REVIEW':fontcolor=white:fontsize=36:box=1:boxcolor=black@0.45:boxborderw=12:x=(w-text_w)/2:y=48"
        )
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
    ]
    if filters:
        cmd.extend(["-vf", ",".join(filters)])
    cmd.extend(
        [
            "-c:v",
            "libx264",
            "-preset",
            str(profile["preset"]),
            "-crf",
            str(profile["crf"]),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )
    completed = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        error = (completed.stderr or completed.stdout or "").strip()
        raise RuntimeError(error[-4000:] or f"export ffmpeg failed for preset={export_preset}")


def create_video_draft_record(
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
        status=VideoDraftStatus.QUEUED.value,
        template_type=template_type,
        tts_voice_key=tts_voice_key,
        burned_caption=burned_caption,
        timeline_json={},
        render_config_json=render_config or {},
        metadata_json={"render_status": "queued"},
    )
    db.add(vd)
    db.commit()
    db.refresh(vd)
    return vd


def render_video_draft(db: Session, video_draft: VideoDraft) -> VideoDraft:
    if video_draft.status == VideoDraftStatus.REJECTED.value:
        raise ValueError("rejected drafts cannot be rerendered")

    candidate = db.get(Candidate, video_draft.candidate_id)
    script_draft = db.get(ScriptDraft, video_draft.script_draft_id)
    if candidate is None or script_draft is None:
        raise ValueError("Candidate or script draft not found")
    video_draft.status = VideoDraftStatus.RUNNING.value
    metadata = dict(video_draft.metadata_json or {})
    metadata["render_status"] = "running"
    metadata.pop("render_error", None)
    video_draft.metadata_json = metadata
    db.add(video_draft)
    db.commit()
    db.refresh(video_draft)
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
        "render_status": "ready",
    }
    db.add(video_draft)
    db.commit()
    db.refresh(video_draft)
    return video_draft


def mark_video_draft_failed(db: Session, video_draft: VideoDraft, *, error_message: str) -> VideoDraft:
    video_draft.status = VideoDraftStatus.FAILED.value
    metadata = dict(video_draft.metadata_json or {})
    metadata["render_status"] = "failed"
    metadata["render_error"] = error_message[:2000]
    video_draft.metadata_json = metadata
    db.add(video_draft)
    db.commit()
    db.refresh(video_draft)
    return video_draft


def create_export_record(
    db: Session,
    *,
    video_draft: VideoDraft,
    export_preset: str,
    include_srt: bool,
    include_script_txt: bool,
    include_metadata_json: bool,
) -> Export:
    exp = Export(
        video_draft_id=video_draft.id,
        status=ExportStatus.QUEUED.value,
        export_preset=export_preset,
        metadata_json={
            "include_srt": include_srt,
            "include_script_txt": include_script_txt,
            "include_metadata_json": include_metadata_json,
            "render_status": "queued",
        },
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def render_export(
    db: Session,
    *,
    export: Export,
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
    export.status = ExportStatus.RUNNING.value
    export_metadata = dict(export.metadata_json or {})
    export_metadata["render_status"] = "running"
    export_metadata.pop("render_error", None)
    export.metadata_json = export_metadata
    db.add(export)
    db.commit()
    db.refresh(export)
    export_version = next_export_version(db, video_draft.id)
    export_dir = (
        Path(video_draft.draft_video_path).resolve().parent.parent / "exports" / f"export_{export_version}"
    )
    export_dir.mkdir(parents=True, exist_ok=True)

    export_video_path = export_dir / f"{export_preset}_v{export_version}.mp4"
    _render_export_video(
        source_path=Path(video_draft.draft_video_path).resolve(),
        output_path=export_video_path,
        export_preset=export_preset,
    )

    export_subtitle_path = None
    if include_srt and video_draft.subtitle_path:
        export_subtitle_path = export_dir / f"{export_preset}_v{export_version}.srt"
        shutil.copy2(video_draft.subtitle_path, export_subtitle_path)

    export_script_path = None
    if include_script_txt:
        script = db.get(ScriptDraft, video_draft.script_draft_id)
        export_script_path = export_dir / f"{export_preset}_script_v{export_version}.txt"
        export_script_path.write_text(
            (script.full_script_text if script else "").strip(),
            encoding="utf-8",
        )

    export_metadata_path = None
    metadata_payload = {
        "export_version": export_version,
        "video_draft_id": video_draft.id,
        "preset_profile": _resolve_export_profile(export_preset),
        "video_draft_metadata": video_draft.metadata_json or {},
        "render_config": video_draft.render_config_json or {},
        "timeline_json": video_draft.timeline_json or {},
    }
    if include_metadata_json:
        export_metadata_path = export_dir / f"{export_preset}_meta_v{export_version}.json"
        export_metadata_path.write_text(json.dumps(metadata_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    export.status = ExportStatus.READY.value
    export.export_preset = export_preset
    export.export_video_path = str(export_video_path.resolve())
    export.export_subtitle_path = str(export_subtitle_path.resolve()) if export_subtitle_path else None
    export.export_script_path = str(export_script_path.resolve()) if export_script_path else None
    export.export_metadata_path = str(export_metadata_path.resolve()) if export_metadata_path else None
    export.file_size_bytes = export_video_path.stat().st_size if export_video_path.is_file() else None
    export.metadata_json = {
        **metadata_payload,
        "render_status": "ready",
    }
    db.add(export)
    db.commit()
    db.refresh(export)
    return export


def mark_export_failed(db: Session, export: Export, *, error_message: str) -> Export:
    export.status = ExportStatus.FAILED.value
    metadata = dict(export.metadata_json or {})
    metadata["render_status"] = "failed"
    metadata["render_error"] = error_message[:2000]
    export.metadata_json = metadata
    db.add(export)
    db.commit()
    db.refresh(export)
    return export


def create_video_draft_render_job(
    db: Session,
    *,
    video_draft: VideoDraft,
    step: str,
) -> Job:
    candidate = db.get(Candidate, video_draft.candidate_id)
    if candidate is None:
        raise ValueError("Candidate not found for video draft")
    return create_job(
        db,
        job_type=JobType.VIDEO_DRAFT_RENDER.value,
        episode_id=candidate.episode_id,
        candidate_id=candidate.id,
        payload={"video_draft_id": video_draft.id, "render_type": "video_draft", "step": step},
    )


def create_export_render_job(db: Session, *, export: Export, candidate_id: str, episode_id: str) -> Job:
    return create_job(
        db,
        job_type=JobType.EXPORT_RENDER.value,
        episode_id=episode_id,
        candidate_id=candidate_id,
        payload={"export_id": export.id, "video_draft_id": export.video_draft_id, "render_type": "export"},
    )
