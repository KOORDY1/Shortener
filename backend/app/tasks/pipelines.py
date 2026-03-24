from __future__ import annotations

from celery import chain

from app.core.celery_app import celery_app
from app.db.models import Episode, EpisodeStatus, Job, ScriptDraft
from app.db.session import SessionLocal
from app.services.analysis_service import (
    compute_signals_step,
    detect_shots_step,
    extract_or_generate_transcript_step,
    generate_candidates_step,
    ingest_episode_step,
    transcode_proxy_step,
)
from app.services.jobs import mark_job_failed, mark_job_running, mark_job_succeeded
from app.services.script_service import generate_script_drafts_for_candidate


def _handle_step_failure(job_id: str, episode_id: str | None, step: str, exc: Exception) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is not None:
            mark_job_failed(db, job, step=step, error_message=str(exc))
        if episode_id is not None:
            episode = db.get(Episode, episode_id)
            if episode is not None:
                episode.status = EpisodeStatus.FAILED.value
                db.add(episode)
                db.commit()


@celery_app.task(name="tasks.ingest_episode")
def ingest_episode(episode_id: str, job_id: str) -> dict:
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is None:
                raise ValueError("Job not found")
            mark_job_running(db, job, step="ingest_episode", progress_percent=10)
            return ingest_episode_step(db, episode_id)
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
        _handle_step_failure(job_id, payload.get("episode_id"), "extract_or_generate_transcript", exc)
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
            drafts = generate_script_drafts_for_candidate(
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
            }
            mark_job_succeeded(db, job, payload=payload)
            return payload
    except Exception as exc:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job is not None:
                mark_job_failed(db, job, step="generate_script_drafts", error_message=str(exc))
        raise


def launch_analysis_pipeline(*, episode_id: str, job_id: str) -> None:
    chain(
        ingest_episode.s(episode_id, job_id),
        transcode_proxy.s(job_id),
        detect_shots.s(job_id),
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
