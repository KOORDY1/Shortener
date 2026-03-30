"""2~4 event beam search 기반 narrative arc 탐색 엔진.

setup_score가 높은 event에서 시작해, escalation/reaction을 거쳐
payoff_score가 높은 event로 끝나는 서사 아크를 찾는다.
contiguous(인접)와 composite(gap 허용) 아크를 모두 탐색한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.services.candidate_events import CandidateEvent, serialize_event

from collections import Counter

BEAM_WIDTH = 16
MAX_ARC_DEPTH = 4
MIN_ARC_EVENTS = 2
MAX_GAP_SEC = 300.0
CONTIGUOUS_GAP_SEC = 12.0
MIN_PAYOFF_THRESHOLD = 0.15
MIN_ENTITY_OVERLAP = 0.0
SETUP_SEED_LIMIT = 20


@dataclass
class ArcCandidate:
    events: list[CandidateEvent]
    arc_scores: dict[str, float]
    arc_form: str  # "contiguous" | "composite"
    arc_reason: str

    @property
    def start_time(self) -> float:
        return self.events[0].start_time

    @property
    def end_time(self) -> float:
        return self.events[-1].end_time

    @property
    def total_arc_score(self) -> float:
        return self.arc_scores.get("total_arc_score", 0.0)


def _frequency_entities(events: list[CandidateEvent], *, limit: int = 8) -> list[str]:
    """arc 전체 events에서 빈도 기반 dominant entity를 추출한다."""
    counts: Counter[str] = Counter()
    for e in events:
        for ent in e.dominant_entities:
            counts[ent] += 1
    return [ent for ent, _ in counts.most_common(limit)]


def _entity_overlap(a: CandidateEvent, b: CandidateEvent) -> float:
    set_a = set(a.dominant_entities)
    set_b = set(b.dominant_entities)
    if not set_a or not set_b:
        return 0.0
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0


def _is_contiguous(prev: CandidateEvent, cur: CandidateEvent) -> bool:
    gap = cur.start_time - prev.end_time
    return gap <= CONTIGUOUS_GAP_SEC


def _score_arc(events: list[CandidateEvent]) -> dict[str, float]:
    if len(events) < MIN_ARC_EVENTS:
        return {"total_arc_score": 0.0}

    first = events[0]
    last = events[-1]
    middle = events[1:-1] if len(events) > 2 else []

    arc_setup_strength = first.setup_score
    arc_payoff_strength = last.payoff_score
    arc_escalation_strength = (
        sum(e.escalation_score for e in middle) / len(middle) if middle else 0.0
    )

    continuity_pairs = []
    for i in range(len(events) - 1):
        continuity_pairs.append(_entity_overlap(events[i], events[i + 1]))
    arc_continuity_score = (
        sum(continuity_pairs) / len(continuity_pairs) if continuity_pairs else 0.0
    )

    arc_standalone_score = sum(e.standalone_score for e in events) / len(events)

    arc_visual_audio_bonus = min(
        0.5,
        max(e.visual_impact_score for e in events) * 0.3
        + max(e.audio_impact_score for e in events) * 0.2,
    )

    avg_ctx_dep = sum(e.context_dependency_score for e in events) / len(events)
    arc_context_penalty = max(0.0, avg_ctx_dep - 0.3) * 0.5

    setup_to_payoff_delta = max(0.0, arc_payoff_strength - arc_setup_strength * 0.3)

    continuity_weight = 0.15 if arc_continuity_score < 0.1 else 0.1
    total = (
        arc_setup_strength * 0.2
        + arc_escalation_strength * 0.1
        + arc_payoff_strength * 0.25
        + setup_to_payoff_delta * 0.1
        + arc_continuity_score * continuity_weight
        + arc_standalone_score * 0.1
        + arc_visual_audio_bonus * 0.1
        - arc_context_penalty
    )

    return {
        "total_arc_score": round(max(0.0, min(1.0, total)), 3),
        "arc_setup_strength": round(arc_setup_strength, 3),
        "arc_escalation_strength": round(arc_escalation_strength, 3),
        "arc_payoff_strength": round(arc_payoff_strength, 3),
        "arc_continuity_score": round(arc_continuity_score, 3),
        "arc_standalone_score": round(arc_standalone_score, 3),
        "arc_visual_audio_bonus": round(arc_visual_audio_bonus, 3),
        "arc_context_penalty": round(arc_context_penalty, 3),
        "setup_to_payoff_delta": round(setup_to_payoff_delta, 3),
    }


def _arc_reason(events: list[CandidateEvent], scores: dict[str, float]) -> str:
    first_kind = events[0].event_kind
    last_kind = events[-1].event_kind
    if scores["arc_payoff_strength"] >= 0.4 and scores["arc_setup_strength"] >= 0.3:
        return f"setup({first_kind})_to_payoff({last_kind})"
    if scores["arc_payoff_strength"] >= 0.3:
        return f"escalation_to_payoff({last_kind})"
    if scores["arc_continuity_score"] >= 0.4:
        return f"entity_continuous_arc({first_kind}_to_{last_kind})"
    return f"dialogue_sequence({first_kind}_to_{last_kind})"


def beam_search_arcs(
    events: Sequence[CandidateEvent],
    *,
    beam_width: int = BEAM_WIDTH,
    max_depth: int = MAX_ARC_DEPTH,
    max_results: int = 20,
) -> list[ArcCandidate]:
    """setup_score 높은 event부터 시작해 2~4 event narrative arc를 beam search로 탐색."""
    if len(events) < MIN_ARC_EVENTS:
        return []

    sorted_by_setup = sorted(events, key=lambda e: e.setup_score, reverse=True)
    seed_events = sorted_by_setup[:SETUP_SEED_LIMIT]

    beams: list[list[CandidateEvent]] = [[e] for e in seed_events]
    completed_arcs: list[ArcCandidate] = []

    for _depth in range(max_depth - 1):
        next_beams: list[tuple[float, list[CandidateEvent]]] = []

        for beam in beams:
            tail = beam[-1]
            for candidate in events:
                if candidate.start_time <= tail.end_time:
                    continue
                gap = candidate.start_time - tail.end_time
                if gap > MAX_GAP_SEC:
                    continue

                overlap = _entity_overlap(tail, candidate)
                if gap > CONTIGUOUS_GAP_SEC and overlap < 0.05:
                    continue

                new_beam = beam + [candidate]
                if len(new_beam) < MIN_ARC_EVENTS:
                    continue

                scores = _score_arc(new_beam)
                is_terminated = (
                    candidate.payoff_score >= MIN_PAYOFF_THRESHOLD
                    or candidate.reaction_score >= 0.3
                    or len(new_beam) >= max_depth
                )

                if is_terminated and scores["total_arc_score"] > 0.05:
                    all_contiguous = all(
                        _is_contiguous(new_beam[i], new_beam[i + 1])
                        for i in range(len(new_beam) - 1)
                    )
                    arc_form = "contiguous" if all_contiguous else "composite"
                    reason = _arc_reason(new_beam, scores)
                    completed_arcs.append(
                        ArcCandidate(
                            events=new_beam,
                            arc_scores=scores,
                            arc_form=arc_form,
                            arc_reason=reason,
                        )
                    )

                if len(new_beam) < max_depth:
                    next_beams.append((scores["total_arc_score"], new_beam))

        next_beams.sort(key=lambda x: x[0], reverse=True)
        beams = [b for _, b in next_beams[:beam_width]]
        if not beams:
            break

    completed_arcs.sort(key=lambda a: a.total_arc_score, reverse=True)
    return completed_arcs[:max_results]


def arc_to_scored_window_metadata(
    arc: ArcCandidate,
    *,
    timeline_end: float = 9999.0,
) -> dict:
    """ArcCandidate를 ScoredWindow의 metadata_json 형식으로 변환.

    core/support padding을 적용해 최소 30초를 보장한다.
    """
    from app.services.candidate_spans import (
        extract_core_support_summary,
        pad_spans_to_minimum,
    )

    events = arc.events
    core_clip_spans: list[dict] = []
    for i, event in enumerate(events):
        is_first = (i == 0)
        is_last = (i == len(events) - 1)
        if is_first:
            role = "core_setup"
        elif is_last:
            role = "core_payoff"
        else:
            role = "core_escalation"
        core_clip_spans.append({
            "start_time": round(event.start_time, 3),
            "end_time": round(event.end_time, 3),
            "order": i,
            "role": role,
        })

    padded_spans, support_added_sec = pad_spans_to_minimum(
        core_clip_spans,
        timeline_start=0.0,
        timeline_end=timeline_end,
    )
    core_support = extract_core_support_summary(padded_spans)

    payoff_event = events[-1]
    excerpt = " ".join(e.text[:80] for e in events)[:320]

    return {
        "generated_by": "arc_beam_search_v1",
        "composite": arc.arc_form == "composite",
        "candidate_track": "dialogue",
        "arc_form": arc.arc_form,
        "arc_reason": arc.arc_reason,
        "arc_event_count": len(events),
        "single_arc_complete_score": round(arc.arc_scores.get("total_arc_score", 0.0), 4),
        "clip_spans": padded_spans,
        "source_events": [serialize_event(e) for e in events],
        "transcript_excerpt": excerpt,
        "dedupe_tokens": sorted(
            set(t for e in events for t in (e.tokens or []))
        )[:16],
        "dominant_entities": _frequency_entities(events, limit=8),
        "ranking_focus": arc.arc_reason.split("(")[0] if "(" in arc.arc_reason else arc.arc_reason,
        "payoff_anchor": {
            "start_time": payoff_event.start_time,
            "end_time": payoff_event.end_time,
            "payoff_score": payoff_event.payoff_score,
            "event_kind": payoff_event.event_kind,
        },
        "support_added_sec": support_added_sec,
        **core_support,
        **arc.arc_scores,
    }
