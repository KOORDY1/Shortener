from __future__ import annotations

from datetime import datetime, timezone

from celery import chain

from app.core.celery_app import celery_app
from app.db.models import Candidate, Episode, EpisodeStatus, Job
from app.db.session import SessionLocal
from app.services.analysis_metadata import mark_analysis_failed
from app.services.analysis_service import (
    compute_signals_step,
    detect_shots_step,
    extract_keyframes_step,
    extract_or_generate_transcript_step,
    generate_candidates_step,
    ingest_episode_step,
    transcode_proxy_step,
)
from app.services.jobs import mark_job_failed, mark_job_running, mark_job_succeeded
from app.services.script_service import generate_script_drafts_for_candidate
from app.services.short_clip_service import render_candidate_short_clip

RENDER_EDITOR_META_KEY = "render_editor"


def _handle_step_failure(job_id: str, episode_id: str | None, step: str, exc: Exception) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is not None:
            mark_job_failed(db, job, step=step, error_message=str(exc))
        if episode_id is not None:
            episode = db.get(Episode, episode_id)
            if episode is not None:
                episode.status = EpisodeStatus.FAILED.value
                mark_analysis_failed(episode, step, str(exc))
                db.add(episode)
                db.commit()


@celery_app.task(name="tasks.ingest_episode")
def ingest_episode(episode_id: str, job_id: str, ignore_cache: bool = False) -> dict:
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise ValueError("Job not found")
            mark_job_running(db, job, step="ingest_episode", progress_percent=10)
            result = ingest_episode_step(db, episode_id)
            return {**result, "ignore_cache": bool(ignore_cache)}
    except Exception as exc:
        _handle_step_failure(job_id, episode_id, "ingest_episode", exc)
        raise


@celery_app.task(name="tasks.transcode_proxy")
def transcode_proxy(payload: dict, job_id: str) -> dict:
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise ValueError("Job not found")
            mark_job_running(db, job, step="transcode_proxy", progress_percent=30)
            return transcode_proxy_step(db, payload)
    except Exception as exc:
        _handle_step_failure(job_id, payload.get("episode_id"), "transcode_proxy", exc)
        raise


@celery_app.task(name="tasks.detect_shots")
def detect_shots(payload: dict, job_id: str) -> dict:
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise ValueError("Job not found")
            mark_job_running(db, job, step="detect_shots", progress_percent=45)
            return detect_shots_step(db, payload)
    except Exception as exc:
        _handle_step_failure(job_id, payload.get("episode_id"), "detect_shots", exc)
        raise


@celery_app.task(name="tasks.extract_or_generate_transcript")
def extract_or_generate_transcript(payload: dict, job_id: str) -> dict:
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise ValueError("Job not found")
            mark_job_running(db, job, step="extract_or_generate_transcript", progress_percent=60)
            return extract_or_generate_transcript_step(db, payload)
    except Exception as exc:
        _handle_step_failure(
            job_id, payload.get("episode_id"), "extract_or_generate_transcript", exc
        )
        raise


@celery_app.task(name="tasks.extract_keyframes")
def extract_keyframes(payload: dict, job_id: str) -> dict:
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise ValueError("Job not found")
            mark_job_running(db, job, step="extract_keyframes", progress_percent=52)
            return extract_keyframes_step(db, payload)
    except Exception as exc:
        _handle_step_failure(job_id, payload.get("episode_id"), "extract_keyframes", exc)
        raise


@celery_app.task(name="tasks.compute_signals")
def compute_signals(payload: dict, job_id: str) -> dict:
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise ValueError("Job not found")
            mark_job_running(db, job, step="compute_signals", progress_percent=75)
            return compute_signals_step(db, payload)
    except Exception as exc:
        _handle_step_failure(job_id, payload.get("episode_id"), "compute_signals", exc)
        raise


@celery_app.task(name="tasks.generate_candidates")
def generate_candidates(payload: dict, job_id: str) -> dict:
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise ValueError("Job not found")
            mark_job_running(db, job, step="generate_candidates", progress_percent=90)
            result = generate_candidates_step(db, payload)
            mark_job_succeeded(db, job, payload=result)
            return result
    except Exception as exc:
        _handle_step_failure(job_id, payload.get("episode_id"), "generate_candidates", exc)
        raise


@celery_app.task(name="tasks.generate_script_drafts")
def generate_script_drafts(
    candidate_id: str,
    job_id: str,
    language: str,
    versions: int,
    tone: str,
    channel_style: str,
    force_regenerate: bool,
) -> dict:
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise ValueError("Job not found")
            mark_job_running(db, job, step="generate_script_drafts", progress_percent=25)
            drafts, generation_meta = generate_script_drafts_for_candidate(
                db,
                candidate_id=candidate_id,
                language=language,
                versions=versions,
                tone=tone,
                channel_style=channel_style,
                force_regenerate=force_regenerate,
            )
            payload = {
                "candidate_id": candidate_id,
                "script_draft_ids": [draft.id for draft in drafts],
                "provider": generation_meta.get("provider"),
                "fallback_reason": generation_meta.get("fallback_reason"),
                "source_error": generation_meta.get("source_error"),
            }
            mark_job_succeeded(db, job, payload=payload)
            return payload
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                mark_job_failed(db, job, step="generate_script_drafts", error_message=str(exc))
        raise


@celery_app.task(name="tasks.render_short_clip")
def render_short_clip_task(
    candidate_id: str,
    job_id: str,
    trim_start: float,
    trim_end: float,
    burn_subtitles: bool,
    width: int,
    height: int,
    fit_mode: str = "contain",
    quality_preset: str = "standard",
    subtitle_style: dict | None = None,
    subtitle_text_overrides: dict | None = None,
    use_imported_subtitles: bool = False,
    use_edited_ass: bool = False,
    output_kind: str = "final",
) -> dict:
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise ValueError("Job not found")
            candidate = db.get(Candidate, candidate_id)
            if candidate is None:
                raise ValueError("Candidate not found")
            mark_job_running(db, job, step="ffmpeg_short_clip", progress_percent=10)
            render_result = render_candidate_short_clip(
                db,
                candidate=candidate,
                trim_start=trim_start,
                trim_end=trim_end,
                burn_subtitles=burn_subtitles,
                width=width,
                height=height,
                fit_mode=fit_mode,
                quality_preset=quality_preset,
                subtitle_style=subtitle_style or {},
                subtitle_text_overrides=subtitle_text_overrides or {},
                use_imported_subtitles=use_imported_subtitles,
                use_edited_ass=use_edited_ass,
                output_kind=output_kind,
            )
            path = str(render_result["path"])
            version = int(render_result["version"])
            rendered_at = datetime.now(timezone.utc).isoformat()
            md = dict(candidate.metadata_json or {})
            editor_meta = dict(md.get(RENDER_EDITOR_META_KEY) or {})
            if output_kind == "preview":
                editor_meta["preview_clip_path"] = path
                editor_meta["preview_clip_version"] = version
                editor_meta["preview_clip_rendered_at"] = rendered_at
                editor_meta.pop("preview_clip_error", None)
                md[RENDER_EDITOR_META_KEY] = editor_meta
            else:
                candidate.short_clip_path = path
                md["short_clip_version"] = version
                md["short_clip_rendered_at"] = rendered_at
                md.pop("short_clip_error", None)
            candidate.metadata_json = md
            db.add(candidate)
            payload = {
                "candidate_id": candidate_id,
                "output_kind": output_kind,
                "clip_path": path,
                "clip_version": version,
                "rendered_at": rendered_at,
            }
            mark_job_succeeded(db, job, payload=payload)
            return payload
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                mark_job_failed(db, job, step="render_short_clip", error_message=str(exc))
            candidate = db.get(Candidate, candidate_id)
            if candidate is not None:
                md = dict(candidate.metadata_json or {})
                if output_kind == "preview":
                    editor_meta = dict(md.get(RENDER_EDITOR_META_KEY) or {})
                    editor_meta["preview_clip_error"] = str(exc)[:2000]
                    md[RENDER_EDITOR_META_KEY] = editor_meta
                else:
                    md["short_clip_error"] = str(exc)[:2000]
                candidate.metadata_json = md
                db.add(candidate)
                db.commit()
        raise


def launch_analysis_pipeline(*, episode_id: str, job_id: str, ignore_cache: bool = False) -> None:
    chain(
        ingest_episode.s(episode_id, job_id, ignore_cache),
        transcode_proxy.s(job_id),
        detect_shots.s(job_id),
        extract_keyframes.s(job_id),
        extract_or_generate_transcript.s(job_id),
        compute_signals.s(job_id),
        generate_candidates.s(job_id),
    ).apply_async()


def launch_script_generation(
    *,
    candidate_id: str,
    job_id: str,
    language: str,
    versions: int,
    tone: str,
    channel_style: str,
    force_regenerate: bool,
) -> None:
    generate_script_drafts.delay(
        candidate_id=candidate_id,
        job_id=job_id,
        language=language,
        versions=versions,
        tone=tone,
        channel_style=channel_style,
        force_regenerate=force_regenerate,
    )


def launch_short_clip_render(
    *,
    candidate_id: str,
    job_id: str,
    trim_start: float,
    trim_end: float,
    burn_subtitles: bool,
    width: int,
    height: int,
    fit_mode: str = "contain",
    quality_preset: str = "standard",
    subtitle_style: dict | None = None,
    subtitle_text_overrides: dict | None = None,
    use_imported_subtitles: bool = False,
    use_edited_ass: bool = False,
    output_kind: str = "final",
) -> None:
    render_short_clip_task.delay(
        candidate_id=candidate_id,
        job_id=job_id,
        trim_start=trim_start,
        trim_end=trim_end,
        burn_subtitles=burn_subtitles,
        width=width,
        height=height,
        fit_mode=fit_mode,
        quality_preset=quality_preset,
        subtitle_style=subtitle_style or {},
        subtitle_text_overrides=subtitle_text_overrides or {},
        use_imported_subtitles=use_imported_subtitles,
        use_edited_ass=use_edited_ass,
        output_kind=output_kind,
    )
