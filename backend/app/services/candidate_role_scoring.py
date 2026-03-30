"""Micro-event 서사 역할 점수 계산.

각 CandidateEvent에 setup / escalation / reaction / payoff / standalone /
context_dependency / visual_impact / audio_impact 8개 점수(0~1)를 부여한다.
"""

from __future__ import annotations

import re
from typing import Sequence

from app.services.candidate_language_signals import normalize_text

PRONOUN_RE = re.compile(
    r"\b(he|she|it|they|him|her|them|this|that|these|those"
    r"|그|그녀|그것|이것|저것|걔|얘|쟤)\b",
    re.IGNORECASE,
)
SETUP_MARKERS = (
    "?",
    "why",
    "what if",
    "imagine",
    "suppose",
    "왜",
    "만약",
    "어떻게",
    "그런데",
    "근데",
    "혹시",
)
ESCALATION_MARKERS = (
    "but",
    "however",
    "wait",
    "actually",
    "worse",
    "even",
    "하지만",
    "근데",
    "더",
    "심지어",
    "게다가",
    "오히려",
)
PAYOFF_MARKERS = (
    "so",
    "finally",
    "turns out",
    "that's why",
    "thats why",
    "told you",
    "결국",
    "그래서",
    "알고 보니",
    "거봐",
    "내가 그랬지",
    "드디어",
)
CONTEXT_DEP_MARKERS = (
    "아까",
    "earlier",
    "before",
    "remember",
    "그때",
    "전에",
    "방금",
)


def _marker_hit(text: str, markers: tuple[str, ...]) -> float:
    normalized = normalize_text(text)
    hits = sum(1 for m in markers if m.lower() in normalized)
    return min(1.0, hits * 0.25)


def _pronoun_ratio(text: str) -> float:
    words = text.split()
    if len(words) < 2:
        return 0.0
    pronoun_count = len(PRONOUN_RE.findall(text))
    return min(1.0, pronoun_count / max(len(words), 1))


def compute_role_scores(
    event: "RoleScoreInput",
    *,
    prev_event: "RoleScoreInput | None" = None,
    next_event: "RoleScoreInput | None" = None,
    is_first: bool = False,
    is_last: bool = False,
    episode_avg_shot_rate: float = 0.0,
    audio_energy_ratio: float = 0.0,
) -> dict[str, float]:
    """Return 8 role scores (0~1) for a single micro-event."""
    signals = event.tone_signals
    text = event.text
    duration = max(0.01, event.end_time - event.start_time)

    # --- setup_score ---
    setup = signals.get("question_signal", 0.0) * 0.35
    setup += signals.get("tension_signal", 0.0) * 0.25
    setup += _marker_hit(text, SETUP_MARKERS) * 0.2
    if text.strip().endswith("?"):
        setup += 0.15
    if is_first:
        setup += 0.05
    setup_score = min(1.0, setup)

    # --- escalation_score ---
    escalation = signals.get("tension_signal", 0.0) * 0.3
    escalation += signals.get("surprise_signal", 0.0) * 0.2
    escalation += _marker_hit(text, ESCALATION_MARKERS) * 0.25
    if prev_event:
        tension_delta = signals.get("tension_signal", 0.0) - prev_event.tone_signals.get(
            "tension_signal", 0.0
        )
        if tension_delta > 0:
            escalation += tension_delta * 0.25
    escalation_score = min(1.0, escalation)

    # --- reaction_score ---
    reaction = signals.get("reaction_signal", 0.0) * 0.35
    reaction += signals.get("surprise_signal", 0.0) * 0.3
    reaction += signals.get("comedy_signal", 0.0) * 0.15
    exclamation_count = text.count("!") + text.count("?!")
    reaction += min(0.2, exclamation_count * 0.07)
    reaction_score = min(1.0, reaction)

    # --- payoff_score ---
    payoff = signals.get("payoff_signal", 0.0) * 0.35
    payoff += signals.get("emotion_signal", 0.0) * 0.15
    payoff += signals.get("reaction_signal", 0.0) * 0.15
    payoff += _marker_hit(text, PAYOFF_MARKERS) * 0.2
    if is_last:
        payoff += 0.1
    if event.event_kind in {"payoff", "reaction", "emotion"}:
        payoff += 0.05
    payoff_score = min(1.0, payoff)

    # --- standalone_score ---
    standalone = 0.0
    if event.cue_count >= 2:
        standalone += 0.2
    if event.dominant_entities:
        standalone += min(0.3, len(event.dominant_entities) * 0.1)
    stripped = text.strip()
    if stripped and stripped[-1] in ".!?":
        standalone += 0.15
    pronoun_r = _pronoun_ratio(text)
    standalone += max(0.0, 0.2 - pronoun_r * 0.4)
    standalone += min(0.15, len(stripped) / 300.0)
    standalone_score = min(1.0, standalone)

    # --- context_dependency_score ---
    ctx_dep = pronoun_r * 0.4
    ctx_dep += _marker_hit(text, CONTEXT_DEP_MARKERS) * 0.3
    if not event.dominant_entities:
        ctx_dep += 0.15
    if event.cue_count <= 1 and len(stripped) < 30:
        ctx_dep += 0.15
    context_dependency_score = min(1.0, ctx_dep)

    # --- visual_impact_score ---
    shot_rate = event.shot_count / duration
    visual = 0.0
    if episode_avg_shot_rate > 0:
        visual = min(1.0, (shot_rate / episode_avg_shot_rate - 1.0) * 0.5) if shot_rate > episode_avg_shot_rate else 0.0
    visual += min(0.3, event.shot_count * 0.06)
    if event.shot_count >= 3 and duration < 8.0:
        visual += 0.2
    visual_impact_score = min(1.0, max(0.0, visual))

    # --- audio_impact_score ---
    audio_impact_score = min(1.0, max(0.0, audio_energy_ratio))

    return {
        "setup_score": round(setup_score, 3),
        "escalation_score": round(escalation_score, 3),
        "reaction_score": round(reaction_score, 3),
        "payoff_score": round(payoff_score, 3),
        "standalone_score": round(standalone_score, 3),
        "context_dependency_score": round(context_dependency_score, 3),
        "visual_impact_score": round(visual_impact_score, 3),
        "audio_impact_score": round(audio_impact_score, 3),
    }


class RoleScoreInput:
    """Duck-type protocol used by compute_role_scores.

    CandidateEvent satisfies this interface.
    """

    start_time: float
    end_time: float
    text: str
    cue_count: int
    shot_count: int
    event_kind: str
    tone_signals: dict[str, float]
    dominant_entities: list[str]
