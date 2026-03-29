from __future__ import annotations

from collections import Counter
from typing import Sequence

from app.services.candidate_events import CandidateEvent
from app.services.candidate_language_signals import answer_marker_score


def _event_duration(event: CandidateEvent) -> float:
    return max(0.0, float(event.end_time) - float(event.start_time))


def dialogue_turn_density(events: Sequence[CandidateEvent], duration_sec: float) -> float:
    cue_count = sum(event.cue_count for event in events)
    if duration_sec <= 0:
        return 0.0
    return min(1.0, (cue_count / duration_sec) * 2.8)


def question_answer_score(events: Sequence[CandidateEvent]) -> float:
    if len(events) < 2:
        return 0.0
    score = 0.0
    for left, right in zip(events, events[1:]):
        if left.tone_signals.get("question_signal", 0.0) >= 0.45:
            score = max(
                score,
                min(
                    1.0,
                    0.45
                    + answer_marker_score(right.text) * 0.55
                    + right.tone_signals.get("payoff_signal", 0.0) * 0.25,
                ),
            )
    return min(1.0, score)


def reaction_shift_score(events: Sequence[CandidateEvent]) -> float:
    if len(events) < 2:
        return events[0].tone_signals.get("reaction_signal", 0.0) if events else 0.0
    split = max(1, len(events) // 2)
    early = events[:split]
    late = events[split:]
    early_level = max(
        (
            event.tone_signals.get("reaction_signal", 0.0)
            + event.tone_signals.get("surprise_signal", 0.0)
        )
        / 2.0
        for event in early
    )
    late_level = max(
        (
            event.tone_signals.get("reaction_signal", 0.0)
            + event.tone_signals.get("surprise_signal", 0.0)
        )
        / 2.0
        for event in late
    )
    return max(0.0, min(1.0, late_level - early_level + 0.35))


def payoff_end_weight(events: Sequence[CandidateEvent]) -> float:
    if not events:
        return 0.0
    tail = events[max(0, len(events) - max(1, len(events) // 3)) :]
    return min(
        1.0,
        max(
            (
                event.tone_signals.get("payoff_signal", 0.0)
                + event.tone_signals.get("emotion_signal", 0.0)
                + event.tone_signals.get("reaction_signal", 0.0)
            )
            / 3.0
            for event in tail
        )
        + (0.15 if tail[-1].event_kind in {"reaction", "payoff", "emotion"} else 0.0),
    )


def entity_consistency(events: Sequence[CandidateEvent]) -> float:
    entity_sets = [set(event.dominant_entities) for event in events if event.dominant_entities]
    if len(entity_sets) < 2:
        return 0.35 if entity_sets else 0.0
    union = set().union(*entity_sets)
    common = set.intersection(*entity_sets)
    if not union:
        return 0.0
    return len(common) / len(union)


def standalone_clarity(events: Sequence[CandidateEvent], speech_coverage: float) -> float:
    if not events:
        return 0.0
    event_bonus = min(1.0, len(events) / 4.0)
    terminal_bonus = 0.2 if events[-1].text.strip().endswith(("?", "!", ".")) else 0.0
    return min(1.0, speech_coverage * 0.55 + event_bonus * 0.25 + terminal_bonus)


def hookability(events: Sequence[CandidateEvent]) -> float:
    if not events:
        return 0.0
    head = events[0]
    return min(
        1.0,
        head.tone_signals.get("question_signal", 0.0) * 0.35
        + head.tone_signals.get("surprise_signal", 0.0) * 0.3
        + head.tone_signals.get("tension_signal", 0.0) * 0.25
        + head.tone_signals.get("reaction_signal", 0.0) * 0.2,
    )


def dominant_focus(events: Sequence[CandidateEvent]) -> str:
    if not events:
        return "dialogue"
    counts = Counter(event.event_kind for event in events)
    most_common_kind = counts.most_common(1)[0][0]
    qa = question_answer_score(events)
    reaction = reaction_shift_score(events)
    payoff = payoff_end_weight(events)
    comedy = max((event.tone_signals.get("comedy_signal", 0.0) for event in events), default=0.0)
    emotion = max((event.tone_signals.get("emotion_signal", 0.0) for event in events), default=0.0)
    tension = max((event.tone_signals.get("tension_signal", 0.0) for event in events), default=0.0)
    if qa >= 0.6 and payoff >= 0.45:
        return "setup_payoff"
    if reaction >= 0.55 and comedy >= 0.45:
        return "awkward_reaction"
    if payoff >= 0.55 and emotion >= 0.45:
        return "emotional_payoff"
    if tension >= 0.55 and payoff >= 0.45:
        return "tension_release"
    if most_common_kind == "reaction":
        return "reaction_turn"
    if most_common_kind == "question":
        return "argument_turn"
    if comedy >= 0.45:
        return "funny_dialogue"
    return most_common_kind
