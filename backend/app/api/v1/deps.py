from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db.models import Candidate, Episode, Export, Job, ScriptDraft, VideoDraft


def get_episode_or_404(db: Session, episode_id: str) -> Episode:
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    return episode


def get_candidate_or_404(db: Session, candidate_id: str) -> Candidate:
    candidate = db.get(Candidate, candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    return candidate


def get_job_or_404(db: Session, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def get_script_draft_or_404(db: Session, script_draft_id: str) -> ScriptDraft:
    draft = db.get(ScriptDraft, script_draft_id)
    if draft is None:
        raise HTTPException(status_code=404, detail="Script draft not found")
    return draft


def get_video_draft_or_404(db: Session, video_draft_id: str) -> VideoDraft:
    vd = db.get(VideoDraft, video_draft_id)
    if vd is None:
        raise HTTPException(status_code=404, detail="Video draft not found")
    return vd


def get_export_or_404(db: Session, export_id: str) -> Export:
    exp = db.get(Export, export_id)
    if exp is None:
        raise HTTPException(status_code=404, detail="Export not found")
    return exp
