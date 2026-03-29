from __future__ import annotations

from app.services.candidate_generation import ScoredWindow

MAX_COMPOSITE_CANDIDATES = 10
MAX_COMPOSITE_INPUTS = 40
MIN_GAP_SEC = 6.0
MAX_GAP_SEC = 420.0
MAX_TOTAL_DURATION_SEC = 64.0


def _tokens(window: ScoredWindow) -> set[str]:
    return {
        str(token)
        for token in (window.metadata_json.get("dedupe_tokens") or [])
        if isinstance(token, str) and token
    }


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _event_kinds(window: ScoredWindow) -> list[str]:
    return [
        str(item.get("event_kind"))
        for item in (window.metadata_json.get("source_events") or [])
        if isinstance(item, dict) and item.get("event_kind")
    ]


def _event_pool(windows: list[ScoredWindow]) -> list[ScoredWindow]:
    pooled: list[ScoredWindow] = []
    seen: set[tuple[int, int]] = set()
    for window in windows:
        for index, event in enumerate(window.metadata_json.get("source_events") or []):
            if not isinstance(event, dict):
                continue
            try:
                start_time = round(float(event.get("start_time")), 3)
                end_time = round(float(event.get("end_time")), 3)
            except (TypeError, ValueError):
                continue
            if end_time <= start_time:
                continue
            key = (int(round(start_time * 100)), int(round(end_time * 100)))
            if key in seen:
                continue
            seen.add(key)
            pooled.append(
                ScoredWindow(
                    start_time=start_time,
                    end_time=end_time,
                    total_score=round(
                        4.0
                        + float(event.get("tone_signals", {}).get("reaction_signal", 0.0) or 0.0) * 2.0
                        + float(event.get("tone_signals", {}).get("payoff_signal", 0.0) or 0.0) * 1.8
                        + float(event.get("tone_signals", {}).get("question_signal", 0.0) or 0.0) * 1.5,
                        2,
                    ),
                    scores_json={"total_score": 5.0},
                    title_hint=str(event.get("text") or f"event-{index}")[:255],
                    metadata_json={
                        "generated_by": "micro_event_pool_v1",
                        "source_events": [event],
                        "dedupe_tokens": event.get("dominant_entities") or [],
                        "dominant_entities": event.get("dominant_entities") or [],
                        "ranking_focus": str(event.get("event_kind") or "event"),
                        "transcript_excerpt": str(event.get("text") or ""),
                    },
                )
            )
    pooled.sort(key=lambda item: item.total_score, reverse=True)
    return pooled[:MAX_COMPOSITE_INPUTS]


def _question_answer_match(left: ScoredWindow, right: ScoredWindow) -> float:
    left_signals = left.metadata_json
    right_signals = right.metadata_json
    if float(left_signals.get("question_answer_score", 0.0) or 0.0) >= 0.45:
        return min(
            1.0,
            0.4
            + float(right_signals.get("payoff_end_weight", 0.0) or 0.0) * 0.35
            + float(right_signals.get("reaction_shift_score", 0.0) or 0.0) * 0.25,
        )
    left_kinds = _event_kinds(left)
    right_kinds = _event_kinds(right)
    if left_kinds and right_kinds and left_kinds[-1] == "question" and right_kinds[0] in {"reaction", "payoff", "dialogue"}:
        return 0.7
    return 0.0


def _reaction_continuity(left: ScoredWindow, right: ScoredWindow) -> float:
    left_tension = float(left.metadata_json.get("tension_signal", 0.0) or 0.0)
    left_surprise = float(left.metadata_json.get("surprise_signal", 0.0) or 0.0)
    right_reaction = float(right.metadata_json.get("reaction_shift_score", 0.0) or 0.0)
    right_payoff = float(right.metadata_json.get("payoff_end_weight", 0.0) or 0.0)
    return min(1.0, left_tension * 0.35 + left_surprise * 0.2 + right_reaction * 0.25 + right_payoff * 0.2)


def _entity_overlap(left: ScoredWindow, right: ScoredWindow) -> float:
    left_entities = set(left.metadata_json.get("dominant_entities") or [])
    right_entities = set(right.metadata_json.get("dominant_entities") or [])
    if not left_entities or not right_entities:
        return 0.0
    return _jaccard(left_entities, right_entities)


def _pair_reason(
    *,
    entity_overlap: float,
    question_answer_match: float,
    reaction_shift: float,
    same_focus: bool,
) -> str:
    if question_answer_match >= 0.65:
        return "question_to_answer"
    if reaction_shift >= 0.65:
        return "tension_to_reaction"
    if entity_overlap >= 0.3 and same_focus:
        return "shared_entity_payoff"
    if same_focus:
        return "shared_focus_followup"
    return "adjacent_dialogue_link"


def build_composite_candidates(windows: list[ScoredWindow]) -> list[ScoredWindow]:
    ordered = sorted(windows, key=lambda item: item.total_score, reverse=True)[:MAX_COMPOSITE_INPUTS]
    ordered.extend(_event_pool(windows))
    ordered.sort(key=lambda item: item.total_score, reverse=True)
    ordered = ordered[:MAX_COMPOSITE_INPUTS]
    composites: list[ScoredWindow] = []

    for left_index, left in enumerate(ordered):
        left_tokens = _tokens(left)
        left_focus = str(left.metadata_json.get("ranking_focus") or "")
        for right in ordered[left_index + 1 :]:
            if right.start_time <= left.end_time:
                continue
            gap = right.start_time - left.end_time
            if gap < MIN_GAP_SEC or gap > MAX_GAP_SEC:
                continue

            total_duration = (left.end_time - left.start_time) + (right.end_time - right.start_time)
            if total_duration > MAX_TOTAL_DURATION_SEC:
                continue

            right_tokens = _tokens(right)
            overlap_score = _jaccard(left_tokens, right_tokens)
            entity_overlap = _entity_overlap(left, right)
            question_answer_match = _question_answer_match(left, right)
            reaction_shift = _reaction_continuity(left, right)
            right_focus = str(right.metadata_json.get("ranking_focus") or "")
            same_focus = left_focus == right_focus and bool(left_focus)
            if max(overlap_score, entity_overlap, question_answer_match, reaction_shift) < 0.12 and not same_focus:
                continue

            gap_bonus = 0.35 if gap <= 45 else 0.18 if gap <= 120 else 0.0
            duration_penalty = 0.0 if total_duration <= 50 else min(0.45, (total_duration - 50) / 30.0)
            total_score = round(
                min(
                    10.0,
                    ((left.total_score + right.total_score) / 2.0)
                    + overlap_score * 0.9
                    + entity_overlap * 0.65
                    + question_answer_match * 0.8
                    + reaction_shift * 0.55
                    + (0.35 if same_focus else 0.0)
                    + gap_bonus
                    - min(0.45, gap / 360.0)
                    - duration_penalty,
                ),
                2,
            )
            pair_reason = _pair_reason(
                entity_overlap=entity_overlap,
                question_answer_match=question_answer_match,
                reaction_shift=reaction_shift,
                same_focus=same_focus,
            )
            left_role = "setup" if question_answer_match >= 0.45 or reaction_shift >= 0.4 else "dialogue"
            right_role = "payoff" if question_answer_match >= 0.45 else "reaction" if reaction_shift >= 0.45 else "followup"
            title_hint = f"{left.title_hint} / {right.title_hint}"
            excerpt = " ".join(
                part
                for part in [
                    str(left.metadata_json.get("transcript_excerpt") or "").strip(),
                    str(right.metadata_json.get("transcript_excerpt") or "").strip(),
                ]
                if part
            )[:280]
            metadata = {
                "generated_by": "composite_pair_v1",
                "composite": True,
                "experimental": True,
                "primary_span_index": 0,
                "clip_spans": [
                    {
                        "start_time": round(left.start_time, 3),
                        "end_time": round(left.end_time, 3),
                        "order": 0,
                        "role": left_role,
                    },
                    {
                        "start_time": round(right.start_time, 3),
                        "end_time": round(right.end_time, 3),
                        "order": 1,
                        "role": right_role,
                    },
                ],
                "transcript_excerpt": excerpt,
                "dedupe_tokens": sorted(left_tokens | right_tokens)[:16],
                "ranking_focus": left_focus or right_focus or "composite",
                "composite_similarity": round(overlap_score, 3),
                "span_gap_sec": round(gap, 3),
                "pair_reason": pair_reason,
                "entity_overlap": round(entity_overlap, 3),
                "question_answer_match": round(question_answer_match, 3),
                "reaction_shift": round(reaction_shift, 3),
                "left_role_score": round(max(question_answer_match, reaction_shift, overlap_score), 3),
                "right_role_score": round(
                    max(
                        float(right.metadata_json.get("payoff_end_weight", 0.0) or 0.0),
                        float(right.metadata_json.get("reaction_shift_score", 0.0) or 0.0),
                        entity_overlap,
                    ),
                    3,
                ),
            }
            scores = {
                **(left.scores_json or {}),
                "total_score": total_score,
                "composite_similarity": round(overlap_score, 3),
                "span_gap_sec": round(gap, 3),
                "entity_overlap": round(entity_overlap, 3),
                "question_answer_match": round(question_answer_match, 3),
                "reaction_shift_score": round(reaction_shift, 3),
            }
            composites.append(
                ScoredWindow(
                    start_time=round(left.start_time, 3),
                    end_time=round(right.end_time, 3),
                    total_score=total_score,
                    scores_json=scores,
                    title_hint=title_hint[:255],
                    metadata_json=metadata,
                )
            )
            if len(composites) >= MAX_COMPOSITE_CANDIDATES:
                return composites
    return composites
