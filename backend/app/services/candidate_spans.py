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


CORE_ROLES = frozenset({
    "core_setup", "core_payoff", "core_escalation", "core_reaction",
    "core_dialogue", "core_followup",
    "main", "setup", "payoff", "reaction", "followup", "dialogue",
})
SUPPORT_ROLES = frozenset({
    "support_pre", "support_post", "support_bridge",
})

MIN_CANDIDATE_DURATION_SEC = 30.0
SUPPORT_PRE_SEC = (3.0, 8.0)
SUPPORT_POST_SEC = (2.0, 6.0)
SUPPORT_BRIDGE_SEC = (2.0, 5.0)


def _spans_total(spans: list[ClipSpan]) -> float:
    return sum(max(0.0, s["end_time"] - s["start_time"]) for s in spans)


def pad_spans_to_minimum(
    spans: list[ClipSpan],
    *,
    timeline_start: float = 0.0,
    timeline_end: float = 9999.0,
    min_duration: float = MIN_CANDIDATE_DURATION_SEC,
) -> tuple[list[ClipSpan], float]:
    """core span들에 support padding을 추가해 min_duration 이상으로 맞춘다.

    Returns (padded_spans, support_added_sec).
    """
    if not spans:
        return spans, 0.0

    current_duration = _spans_total(spans)
    if current_duration >= min_duration:
        return spans, 0.0

    result = list(spans)
    result.sort(key=lambda s: (s["order"], s["start_time"]))
    added_sec = 0.0
    deficit = min_duration - current_duration

    # support_pre: 첫 span 앞에 맥락 추가
    if deficit > 0:
        first = result[0]
        pre_budget = min(SUPPORT_PRE_SEC[1], deficit, first["start_time"] - timeline_start)
        pre_budget = max(0.0, pre_budget)
        if pre_budget >= SUPPORT_PRE_SEC[0]:
            pre_span: ClipSpan = {
                "start_time": round(first["start_time"] - pre_budget, 3),
                "end_time": round(first["start_time"], 3),
                "order": first["order"] - 1,
                "role": "support_pre",
            }
            result.insert(0, pre_span)
            added_sec += pre_budget
            deficit -= pre_budget

    # support_post: 마지막 span 뒤에 여운 추가
    if deficit > 0:
        last = result[-1]
        post_budget = min(SUPPORT_POST_SEC[1], deficit, timeline_end - last["end_time"])
        post_budget = max(0.0, post_budget)
        if post_budget >= SUPPORT_POST_SEC[0]:
            post_span: ClipSpan = {
                "start_time": round(last["end_time"], 3),
                "end_time": round(last["end_time"] + post_budget, 3),
                "order": last["order"] + 1,
                "role": "support_post",
            }
            result.append(post_span)
            added_sec += post_budget
            deficit -= post_budget

    # support_bridge: 중간 gap에 bridge 추가
    if deficit > 0 and len(result) >= 2:
        bridged: list[ClipSpan] = [result[0]]
        for i in range(1, len(result)):
            gap = result[i]["start_time"] - result[i - 1]["end_time"]
            if gap >= SUPPORT_BRIDGE_SEC[0] and deficit > 0:
                bridge_len = min(SUPPORT_BRIDGE_SEC[1], gap, deficit)
                if bridge_len >= SUPPORT_BRIDGE_SEC[0]:
                    bridge_span: ClipSpan = {
                        "start_time": round(result[i - 1]["end_time"], 3),
                        "end_time": round(result[i - 1]["end_time"] + bridge_len, 3),
                        "order": result[i - 1]["order"],
                        "role": "support_bridge",
                    }
                    bridged.append(bridge_span)
                    added_sec += bridge_len
                    deficit -= bridge_len
            bridged.append(result[i])
        result = bridged

    # 그래도 부족하면 pre/post를 더 넉넉히 확장
    if deficit > 0:
        first = result[0]
        extra_pre = min(deficit, first["start_time"] - timeline_start)
        if extra_pre > 0.5:
            result[0] = {
                **first,
                "start_time": round(first["start_time"] - extra_pre, 3),
            }
            added_sec += extra_pre
            deficit -= extra_pre

    if deficit > 0:
        last = result[-1]
        extra_post = min(deficit, timeline_end - last["end_time"])
        if extra_post > 0.5:
            result[-1] = {
                **last,
                "end_time": round(last["end_time"] + extra_post, 3),
            }
            added_sec += extra_post

    result.sort(key=lambda s: (s["order"], s["start_time"]))
    for idx, span in enumerate(result):
        span["order"] = idx

    return result, round(added_sec, 3)


def extract_core_support_summary(spans: list[ClipSpan]) -> dict:
    """spans에서 core/support 구분 요약을 반환한다."""
    core_spans = [s for s in spans if (s.get("role") or "main") in CORE_ROLES]
    support_spans = [s for s in spans if (s.get("role") or "") in SUPPORT_ROLES]
    return {
        "core_spans": [
            {"start_time": s["start_time"], "end_time": s["end_time"], "role": s["role"]}
            for s in core_spans
        ],
        "support_spans": [
            {"start_time": s["start_time"], "end_time": s["end_time"], "role": s["role"]}
            for s in support_spans
        ],
        "core_duration_sec": round(_spans_total(core_spans), 3),
        "support_duration_sec": round(_spans_total(support_spans), 3),
        "total_duration_sec": round(_spans_total(spans), 3),
    }
