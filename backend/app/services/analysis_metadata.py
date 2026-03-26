from __future__ import annotations

from typing import Any

from app.core.config import get_settings
from app.db.models import Episode


def _pipeline_meta(episode: Episode) -> tuple[dict[str, Any], dict[str, Any]]:
    meta = dict(episode.metadata_json or {})
    pipeline = dict(meta.get("analysis_pipeline") or {})
    settings = get_settings()
    pipeline["version"] = str(settings.analysis_pipeline_version or "analysis_pipeline_v1")
    pipeline.setdefault("status", "running")
    pipeline.setdefault("steps", {})
    meta["analysis_pipeline"] = pipeline
    return meta, pipeline


def mark_analysis_running(
    episode: Episode,
    step_name: str,
    *,
    step_details: dict[str, Any] | None = None,
) -> None:
    meta, pipeline = _pipeline_meta(episode)
    steps = dict(pipeline.get("steps") or {})
    step = dict(steps.get(step_name) or {})
    step["status"] = "running"
    if step_details:
        step.update(step_details)
    steps[step_name] = step
    pipeline["status"] = "running"
    pipeline["current_step"] = step_name
    pipeline["steps"] = steps
    meta["analysis_pipeline"] = pipeline
    episode.metadata_json = meta


def mark_analysis_completed(
    episode: Episode,
    step_name: str,
    *,
    step_details: dict[str, Any] | None = None,
    pipeline_status: str | None = None,
) -> None:
    meta, pipeline = _pipeline_meta(episode)
    steps = dict(pipeline.get("steps") or {})
    step = dict(steps.get(step_name) or {})
    step["status"] = "completed"
    if step_details:
        step.update(step_details)
    steps[step_name] = step
    pipeline["status"] = pipeline_status or "running"
    pipeline["current_step"] = step_name
    pipeline["steps"] = steps
    meta["analysis_pipeline"] = pipeline
    episode.metadata_json = meta


def mark_analysis_failed(episode: Episode, step_name: str, error_message: str) -> None:
    meta, pipeline = _pipeline_meta(episode)
    steps = dict(pipeline.get("steps") or {})
    step = dict(steps.get(step_name) or {})
    step["status"] = "failed"
    step["error"] = error_message[:500]
    steps[step_name] = step
    pipeline["status"] = "failed"
    pipeline["current_step"] = step_name
    pipeline["steps"] = steps
    meta["analysis_pipeline"] = pipeline
    episode.metadata_json = meta
