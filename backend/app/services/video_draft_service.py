from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Candidate,
    Export,
    ExportStatus,
    Job,
    JobType,
    ScriptDraft,
    VideoDraft,
    VideoDraftStatus,
)
from app.services.jobs import create_job, mark_job_running, mark_job_succeeded
from app.services.storage_service import write_placeholder


def next_video_draft_version(db: Session, candidate_id: str) -> int:
    current = db.scalar(
        select(func.coalesce(func.max(VideoDraft.version_no), 0)).where(
            VideoDraft.candidate_id == candidate_id
        )
    )
    return int(current or 0) + 1


def create_mock_video_draft(
    db: Session,
    *,
    candidate: Candidate,
    script_draft: ScriptDraft,
    template_type: str,
    tts_voice_key: str | None,
    burned_caption: bool,
) -> VideoDraft:
    version_no = next_video_draft_version(db, candidate.id)
    vd = VideoDraft(
        candidate_id=candidate.id,
        script_draft_id=script_draft.id,
        version_no=version_no,
        status=VideoDraftStatus.READY.value,
        template_type=template_type,
        tts_voice_key=tts_voice_key,
        burned_caption=burned_caption,
        draft_video_path=write_placeholder(
            candidate.episode_id,
            ["candidates", candidate.id, "video_drafts", str(version_no), "draft.mp4"],
            "mock draft video placeholder",
        ),
        subtitle_path=write_placeholder(
            candidate.episode_id,
            ["candidates", candidate.id, "video_drafts", str(version_no), "draft.srt"],
            "mock subtitle placeholder",
        ),
        thumbnail_path=write_placeholder(
            candidate.episode_id,
            ["candidates", candidate.id, "video_drafts", str(version_no), "thumb.jpg"],
            "mock thumbnail placeholder",
        ),
        timeline_json={"tracks": [], "mock": True},
        render_config_json={"mock_render": True},
    )
    db.add(vd)
    db.commit()
    db.refresh(vd)
    return vd


def create_mock_export(
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
    episode_id = candidate.episode_id
    base = ["candidates", video_draft.candidate_id, "exports", video_draft.id]

    exp = Export(
        video_draft_id=video_draft.id,
        status=ExportStatus.READY.value,
        export_preset=export_preset,
        export_video_path=write_placeholder(
            episode_id,
            [*base, "final.mp4"],
            "mock export video",
        ),
        export_subtitle_path=(
            write_placeholder(episode_id, [*base, "final.srt"], "mock export srt")
            if include_srt
            else None
        ),
        export_script_path=(
            write_placeholder(episode_id, [*base, "script.txt"], "mock export script")
            if include_script_txt
            else None
        ),
        export_metadata_path=(
            write_placeholder(episode_id, [*base, "meta.json"], '{"mock":true}')
            if include_metadata_json
            else None
        ),
        metadata_json={"include_srt": include_srt, "mock": True},
    )
    db.add(exp)
    db.commit()
    db.refresh(exp)
    return exp


def run_mock_rerender(db: Session, video_draft: VideoDraft) -> tuple[Job, VideoDraft]:
    """Create a VIDEO_DRAFT_RENDER job and complete it immediately (no real FFmpeg)."""
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
        payload={"video_draft_id": video_draft.id, "mock_rerender": True},
    )
    mark_job_running(db, job, step="mock_render", progress_percent=50)

    video_draft.status = VideoDraftStatus.READY.value
    video_draft.draft_video_path = write_placeholder(
        candidate.episode_id,
        [
            "candidates",
            candidate.id,
            "video_drafts",
            str(video_draft.version_no),
            "draft_rerender.mp4",
        ],
        "mock rerender placeholder",
    )
    db.add(video_draft)
    db.commit()
    db.refresh(video_draft)

    mark_job_succeeded(db, job, payload={"video_draft_id": video_draft.id})
    return job, video_draft
