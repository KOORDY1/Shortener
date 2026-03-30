from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from app.db.models import Shot, TranscriptSegment
from app.services.candidate_language_signals import (
    answer_marker_score,
    dominant_entities,
    extract_token_stream,
    extract_tokens,
    tone_signals,
)

MIN_EVENT_SEC = 4.0
MAX_EVENT_SEC = 18.0
MAX_EVENTS_PER_WINDOW = 10


@dataclass
class CandidateEvent:
    start_time: float
    end_time: float
    text: str
    cue_count: int
    shot_count: int
    event_kind: str
    tone_signals: dict[str, float]
    tokens: list[str]
    dominant_entities: list[str]
    source_segments: list[dict[str, Any]]
    # narrative role scores (0~1)
    setup_score: float = 0.0
    escalation_score: float = 0.0
    reaction_score: float = 0.0
    payoff_score: float = 0.0
    standalone_score: float = 0.0
    context_dependency_score: float = 0.0
    visual_impact_score: float = 0.0
    audio_impact_score: float = 0.0


def _shot_count_in_range(shots: Sequence[Shot], start_time: float, end_time: float) -> int:
    return sum(
        1
        for shot in shots
        if float(shot.start_time) <= end_time and float(shot.end_time) >= start_time
    )


def _is_boundary(
    current_text: str,
    next_text: str | None,
    *,
    current_duration: float,
    gap_to_next: float,
) -> bool:
    stripped = current_text.strip()
    if current_duration >= MAX_EVENT_SEC:
        return True
    if gap_to_next >= 1.8 and current_duration >= MIN_EVENT_SEC:
        return True
    if any(stripped.endswith(token) for token in ("?", "!", ".", "?!", "!?")) and current_duration >= MIN_EVENT_SEC:
        return True
    current_signals = tone_signals(current_text)
    next_signals = tone_signals(next_text or "")
    if current_signals["reaction_signal"] >= 0.45 and current_duration >= MIN_EVENT_SEC:
        return True
    if current_signals["payoff_signal"] >= 0.45 and current_duration >= MIN_EVENT_SEC:
        return True
    if current_signals["question_signal"] >= 0.45 and answer_marker_score(next_text or "") >= 0.5:
        return True
    if current_duration >= MIN_EVENT_SEC and next_signals["reaction_signal"] >= 0.5:
        return True
    return False


def _event_kind(text: str, signals: dict[str, float]) -> str:
    if signals["question_signal"] >= 0.45:
        return "question"
    if signals["reaction_signal"] >= 0.5 or signals["surprise_signal"] >= 0.5:
        return "reaction"
    if signals["payoff_signal"] >= 0.45:
        return "payoff"
    if signals["tension_signal"] >= 0.45:
        return "tension"
    if signals["emotion_signal"] >= 0.45:
        return "emotion"
    if signals["comedy_signal"] >= 0.45:
        return "funny_dialogue"
    return "dialogue"


def _build_event(
    segments: Sequence[TranscriptSegment],
    shots: Sequence[Shot],
) -> CandidateEvent | None:
    if not segments:
        return None
    start_time = float(segments[0].start_time)
    end_time = float(segments[-1].end_time)
    if end_time <= start_time:
        return None
    text = "\n".join((segment.text or "").strip() for segment in segments if (segment.text or "").strip())
    signals = tone_signals(text)
    tokens = extract_tokens(text)
    raw_stream = extract_token_stream(text)
    return CandidateEvent(
        start_time=round(start_time, 3),
        end_time=round(end_time, 3),
        text=text,
        cue_count=len(segments),
        shot_count=_shot_count_in_range(shots, start_time, end_time),
        event_kind=_event_kind(text, signals),
        tone_signals=signals,
        tokens=tokens,
        dominant_entities=dominant_entities(raw_stream),
        source_segments=[
            {
                "id": segment.id,
                "start_time": float(segment.start_time),
                "end_time": float(segment.end_time),
                "text": segment.text,
            }
            for segment in segments
        ],
    )


def _apply_role_scores(
    events: list[CandidateEvent],
    shots: Sequence[Shot],
) -> None:
    """Compute and assign role scores to every event in-place."""
    from app.services.candidate_role_scoring import compute_role_scores

    total_duration = max(
        0.01,
        (events[-1].end_time - events[0].start_time) if events else 1.0,
    )
    total_shots = sum(e.shot_count for e in events)
    episode_avg_shot_rate = total_shots / total_duration

    for idx, event in enumerate(events):
        prev_ev = events[idx - 1] if idx > 0 else None
        next_ev = events[idx + 1] if idx + 1 < len(events) else None
        scores = compute_role_scores(
            event,
            prev_event=prev_ev,
            next_event=next_ev,
            is_first=(idx == 0),
            is_last=(idx == len(events) - 1),
            episode_avg_shot_rate=episode_avg_shot_rate,
        )
        event.setup_score = scores["setup_score"]
        event.escalation_score = scores["escalation_score"]
        event.reaction_score = scores["reaction_score"]
        event.payoff_score = scores["payoff_score"]
        event.standalone_score = scores["standalone_score"]
        event.context_dependency_score = scores["context_dependency_score"]
        event.visual_impact_score = scores["visual_impact_score"]
        event.audio_impact_score = scores["audio_impact_score"]


def build_micro_events(
    segments: Sequence[TranscriptSegment],
    shots: Sequence[Shot],
) -> list[CandidateEvent]:
    if not segments:
        return []
    events: list[CandidateEvent] = []
    bucket: list[TranscriptSegment] = []
    for index, segment in enumerate(segments):
        bucket.append(segment)
        start_time = float(bucket[0].start_time)
        end_time = float(bucket[-1].end_time)
        current_duration = max(0.0, end_time - start_time)
        next_segment = segments[index + 1] if index + 1 < len(segments) else None
        gap_to_next = (
            max(0.0, float(next_segment.start_time) - float(segment.end_time)) if next_segment else 999.0
        )
        if _is_boundary(
            (segment.text or "").strip(),
            (next_segment.text or "").strip() if next_segment else None,
            current_duration=current_duration,
            gap_to_next=gap_to_next,
        ):
            event = _build_event(bucket, shots)
            if event is not None:
                events.append(event)
            bucket = []
    if bucket:
        event = _build_event(bucket, shots)
        if event is not None:
            events.append(event)

    merged: list[CandidateEvent] = []
    for event in events:
        if not merged:
            merged.append(event)
            continue
        previous = merged[-1]
        if (event.end_time - event.start_time) < MIN_EVENT_SEC and (
            event.end_time - previous.start_time
        ) <= MAX_EVENT_SEC:
            combined_segments = previous.source_segments + event.source_segments
            merged_event = _build_event(
                [
                    TranscriptSegment(
                        id=str(item["id"]),
                        episode_id="",
                        segment_index=index,
                        start_time=float(item["start_time"]),
                        end_time=float(item["end_time"]),
                        text=str(item["text"]),
                        speaker_label=None,
                    )
                    for index, item in enumerate(combined_segments, start=1)
                ],
                shots,
            )
            if merged_event is not None:
                merged[-1] = merged_event
        else:
            merged.append(event)

    if merged:
        _apply_role_scores(merged, shots)

    return merged


def serialize_event(event: CandidateEvent) -> dict[str, Any]:
    return {
        "start_time": event.start_time,
        "end_time": event.end_time,
        "duration_sec": round(event.end_time - event.start_time, 3),
        "text": event.text[:240],
        "cue_count": event.cue_count,
        "shot_count": event.shot_count,
        "event_kind": event.event_kind,
        "tone_signals": event.tone_signals,
        "dominant_entities": event.dominant_entities,
        "setup_score": event.setup_score,
        "escalation_score": event.escalation_score,
        "reaction_score": event.reaction_score,
        "payoff_score": event.payoff_score,
        "standalone_score": event.standalone_score,
        "context_dependency_score": event.context_dependency_score,
        "visual_impact_score": event.visual_impact_score,
        "audio_impact_score": event.audio_impact_score,
    }
