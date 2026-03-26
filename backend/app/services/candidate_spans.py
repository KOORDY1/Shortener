from __future__ import annotations

from typing import Any, TypedDict

from app.db.models import Candidate


class ClipSpan(TypedDict):
    start_time: float
    end_time: float
    order: int
    role: str | None


def normalize_clip_spans(
    raw_spans: list[dict[str, Any]] | None,
    *,
    default_start: float,
    default_end: float,
) -> list[ClipSpan]:
    normalized: list[ClipSpan] = []
    for index, raw in enumerate(raw_spans or []):
        try:
            start_time = float(raw.get("start_time"))
            end_time = float(raw.get("end_time"))
        except (TypeError, ValueError):
            continue
        if end_time <= start_time:
            continue
        role = raw.get("role")
        normalized.append(
            {
                "start_time": round(start_time, 3),
                "end_time": round(end_time, 3),
                "order": int(raw.get("order", index)),
                "role": str(role) if role is not None else None,
            }
        )
    normalized.sort(key=lambda item: (item["order"], item["start_time"], item["end_time"]))
    if normalized:
        return normalized
    return [
        {
            "start_time": round(float(default_start), 3),
            "end_time": round(float(default_end), 3),
            "order": 0,
            "role": "main",
        }
    ]


def candidate_clip_spans(candidate: Candidate) -> list[ClipSpan]:
    metadata = candidate.metadata_json or {}
    return normalize_clip_spans(
        metadata.get("clip_spans"),
        default_start=float(candidate.start_time),
        default_end=float(candidate.end_time),
    )


def clip_spans_total_duration(spans: list[ClipSpan]) -> float:
    return round(sum(max(0.0, span["end_time"] - span["start_time"]) for span in spans), 3)


def is_composite_candidate(candidate: Candidate) -> bool:
    metadata = candidate.metadata_json or {}
    return bool(metadata.get("composite"))
