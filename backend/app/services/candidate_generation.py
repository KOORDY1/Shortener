"""내용 구조 중심 contiguous 후보 생성기."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Episode, Shot, TranscriptSegment
from app.services.candidate_events import (
    MAX_EVENTS_PER_WINDOW,
    CandidateEvent,
    build_micro_events,
    serialize_event,
)
from app.services.candidate_language_signals import (
    detect_language_hint,
    dominant_entities,
    extract_tokens,
)
from app.services.candidate_structure_signals import (
    dialogue_turn_density,
    dominant_focus,
    entity_consistency,
    hookability,
    payoff_end_weight,
    question_answer_score,
    reaction_shift_score,
    standalone_clarity,
)

MIN_WINDOW_SEC = 30.0
MAX_WINDOW_SEC = 180.0

MAX_CANDIDATES = 14
NMS_IOU_THRESHOLD = 0.52
TEXT_DEDUPE_JACCARD_THRESHOLD = 0.82
TEXT_DEDUPE_MAX_START_GAP_SEC = 20.0
TEXT_DEDUPE_MIN_OVERLAP_SEC = 8.0


@dataclass
class ScoredWindow:
    start_time: float
    end_time: float
    total_score: float
    scores_json: dict[str, float]
    title_hint: str
    metadata_json: dict


@dataclass
class WindowSeed:
    start_time: float
    end_time: float
    events: list[CandidateEvent]
    window_reason: str


def _episode_timeline_end(
    episode: Episode, shots: Sequence[Shot], segments: Sequence[TranscriptSegment]
) -> float:
    timeline_end = float(episode.duration_seconds or 0.0)
    if shots:
        timeline_end = max(timeline_end, max(float(shot.end_time) for shot in shots))
    if segments:
        timeline_end = max(timeline_end, max(float(segment.end_time) for segment in segments))
    return max(timeline_end, MIN_WINDOW_SEC)


def _merged_speech_coverage(segments: Sequence[TranscriptSegment], start: float, end: float) -> float:
    duration = end - start
    if duration <= 0:
        return 0.0
    intervals: list[tuple[float, float]] = []
    for segment in segments:
        lo = max(float(segment.start_time), start)
        hi = min(float(segment.end_time), end)
        if hi > lo:
            intervals.append((lo, hi))
    if not intervals:
        return 0.0
    intervals.sort()
    merged = 0.0
    cur_lo, cur_hi = intervals[0]
    for lo, hi in intervals[1:]:
        if lo <= cur_hi:
            cur_hi = max(cur_hi, hi)
        else:
            merged += cur_hi - cur_lo
            cur_lo, cur_hi = lo, hi
    merged += cur_hi - cur_lo
    return min(1.0, merged / duration)


def _cuts_inside(shots: Sequence[Shot], start: float, end: float) -> int:
    return sum(
        1
        for shot in shots
        if float(shot.start_time) > start + 0.05 and float(shot.start_time) < end - 0.05
    )


def _chars_in_window(segments: Sequence[TranscriptSegment], start: float, end: float) -> int:
    return sum(
        len((segment.text or "").strip())
        for segment in segments
        if min(float(segment.end_time), end) > max(float(segment.start_time), start)
    )


def _title_from_segments(
    segments: Sequence[TranscriptSegment], start: float, end: float, *, max_parts: int = 3
) -> str:
    parts: list[str] = []
    for segment in segments:
        if float(segment.end_time) <= start or float(segment.start_time) >= end:
            continue
        text = (segment.text or "").strip().replace("\n", " ")
        if text:
            parts.append(text)
        if len(parts) >= max_parts:
            break
    if not parts:
        return f"구간 {start:.1f}–{end:.1f}s"
    title_hint = " · ".join(parts)
    return title_hint[:255]


def _excerpt_from_segments(
    segments: Sequence[TranscriptSegment], start: float, end: float, max_chars: int = 320
) -> str:
    parts: list[str] = []
    total = 0
    for segment in segments:
        if float(segment.end_time) <= start or float(segment.start_time) >= end:
            continue
        text = (segment.text or "").strip().replace("\n", " ")
        if not text:
            continue
        parts.append(text)
        total += len(text) + 1
        if total >= max_chars:
            break
    return " ".join(parts)[:max_chars]


def _jaccard_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    if not left or not right:
        return 0.0
    left_set = set(left)
    right_set = set(right)
    union = left_set | right_set
    if not union:
        return 0.0
    return len(left_set & right_set) / len(union)


def _is_text_near_duplicate(candidate: ScoredWindow, kept: ScoredWindow) -> bool:
    candidate_text = str(candidate.metadata_json.get("transcript_excerpt") or candidate.title_hint)
    kept_text = str(kept.metadata_json.get("transcript_excerpt") or kept.title_hint)
    candidate_tokens = candidate.metadata_json.get("dedupe_tokens") or extract_tokens(candidate_text)
    kept_tokens = kept.metadata_json.get("dedupe_tokens") or extract_tokens(kept_text)
    similarity = _jaccard_similarity(candidate_tokens, kept_tokens)
    if similarity < TEXT_DEDUPE_JACCARD_THRESHOLD:
        return False
    overlap = max(
        0.0,
        min(candidate.end_time, kept.end_time) - max(candidate.start_time, kept.start_time),
    )
    start_gap = abs(candidate.start_time - kept.start_time)
    return overlap >= TEXT_DEDUPE_MIN_OVERLAP_SEC or start_gap <= TEXT_DEDUPE_MAX_START_GAP_SEC


def _iou_time(left_start: float, left_end: float, right_start: float, right_end: float) -> float:
    overlap = max(0.0, min(left_end, right_end) - max(left_start, right_start))
    if overlap <= 0:
        return 0.0
    union = max(left_end, right_end) - min(left_start, right_start)
    return overlap / union if union > 0 else 0.0


def _is_duplicate_candidate(candidate: ScoredWindow, kept: Sequence[ScoredWindow]) -> bool:
    candidate_is_composite = bool(candidate.metadata_json.get("composite"))
    for item in kept:
        item_is_composite = bool(item.metadata_json.get("composite"))
        if not candidate_is_composite and not item_is_composite:
            if (
                _iou_time(candidate.start_time, candidate.end_time, item.start_time, item.end_time)
                >= NMS_IOU_THRESHOLD
            ):
                return True
        candidate_spans = candidate.metadata_json.get("clip_spans")
        item_spans = item.metadata_json.get("clip_spans")
        if candidate_spans and item_spans and candidate_spans == item_spans:
            return True
    return any(_is_text_near_duplicate(candidate, item) for item in kept)


def dedupe_scored_windows(
    windows: list[ScoredWindow], limit: int = MAX_CANDIDATES
) -> list[ScoredWindow]:
    ordered = sorted(windows, key=lambda window: -window.total_score)
    kept: list[ScoredWindow] = []
    for window in ordered:
        if _is_duplicate_candidate(window, kept):
            continue
        kept.append(window)
        if len(kept) >= limit:
            break
    return kept


def _shot_window_fallback(shots: Sequence[Shot], timeline_end: float) -> list[WindowSeed]:
    seeds: list[WindowSeed] = []
    for start_index, start_shot in enumerate(shots):
        for end_index in range(start_index, min(len(shots), start_index + 14)):
            end_time = float(shots[end_index].end_time)
            duration = end_time - float(start_shot.start_time)
            if duration > MAX_WINDOW_SEC:
                break
            if duration < MIN_WINDOW_SEC:
                continue
            if duration <= 75.0 or end_index - start_index <= 8:
                seeds.append(
                    WindowSeed(
                        start_time=round(float(start_shot.start_time), 3),
                        end_time=round(end_time, 3),
                        events=[],
                        window_reason="shot_boundary_fallback",
                    )
                )
    if not seeds and timeline_end >= MIN_WINDOW_SEC:
        seeds.append(
            WindowSeed(
                start_time=0.0,
                end_time=min(timeline_end, MAX_WINDOW_SEC),
                events=[],
                window_reason="timeline_fallback",
            )
        )
    return seeds


def _event_window_reason(events: Sequence[CandidateEvent]) -> str | None:
    if not events:
        return None
    qa_score = question_answer_score(events)
    reaction_score = reaction_shift_score(events)
    payoff_score = payoff_end_weight(events)
    hook_score = hookability(events)
    tail_kind = events[-1].event_kind
    if qa_score >= 0.45:
        return "question_answer"
    if reaction_score >= 0.42:
        return "reaction_shift"
    if payoff_score >= 0.45:
        return "payoff_end"
    if hook_score >= 0.45 and len(events) <= 4:
        return "hook_open"
    if tail_kind in {"reaction", "payoff", "emotion", "tension"}:
        return f"tail_{tail_kind}"
    if len(events) <= 3:
        return "compact_dialogue_turn"
    return None


def _enumerate_windows(
    timeline_end: float,
    segments: list[TranscriptSegment],
    shots: list[Shot],
) -> list[WindowSeed]:
    seen: set[tuple[int, int]] = set()
    seeds: list[WindowSeed] = []
    events = build_micro_events(segments, shots)

    def add_seed(start: float, end: float, event_slice: Sequence[CandidateEvent], reason: str) -> None:
        start = max(0.0, float(start))
        end = min(float(timeline_end), float(end))
        if end - start < MIN_WINDOW_SEC or end - start > MAX_WINDOW_SEC:
            return
        key = (int(round(start * 100)), int(round(end * 100)))
        if key in seen:
            return
        seen.add(key)
        seeds.append(
            WindowSeed(
                start_time=round(start, 3),
                end_time=round(end, 3),
                events=list(event_slice),
                window_reason=reason,
            )
        )

    if events:
        for start_index in range(len(events)):
            for end_index in range(start_index, min(len(events), start_index + MAX_EVENTS_PER_WINDOW)):
                event_slice = events[start_index : end_index + 1]
                start_time = event_slice[0].start_time
                end_time = event_slice[-1].end_time
                duration = end_time - start_time
                if duration > MAX_WINDOW_SEC:
                    break
                if duration < MIN_WINDOW_SEC:
                    continue
                reason = _event_window_reason(event_slice)
                if reason:
                    add_seed(start_time, end_time, event_slice, reason)
        if seeds:
            return seeds
    return _shot_window_fallback(shots, timeline_end)


def score_window(
    seed: WindowSeed,
    segments: Sequence[TranscriptSegment],
    shots: Sequence[Shot],
) -> ScoredWindow | None:
    duration = seed.end_time - seed.start_time
    if duration < MIN_WINDOW_SEC or duration > MAX_WINDOW_SEC:
        return None

    speech_coverage = _merged_speech_coverage(segments, seed.start_time, seed.end_time)
    char_count = _chars_in_window(segments, seed.start_time, seed.end_time)
    char_rate = char_count / max(duration, 1.0)
    cuts_inside = _cuts_inside(shots, seed.start_time, seed.end_time)
    excerpt = _excerpt_from_segments(segments, seed.start_time, seed.end_time)
    tokens = extract_tokens(excerpt)
    all_entities = dominant_entities(tokens, limit=8)
    events = seed.events

    if events:
        comedy_signal = max((event.tone_signals["comedy_signal"] for event in events), default=0.0)
        emotion_signal = max((event.tone_signals["emotion_signal"] for event in events), default=0.0)
        surprise_signal = max((event.tone_signals["surprise_signal"] for event in events), default=0.0)
        tension_signal = max((event.tone_signals["tension_signal"] for event in events), default=0.0)
        reaction_signal = max((event.tone_signals["reaction_signal"] for event in events), default=0.0)
        payoff_signal = max((event.tone_signals["payoff_signal"] for event in events), default=0.0)
        question_signal = max((event.tone_signals["question_signal"] for event in events), default=0.0)
    else:
        comedy_signal = emotion_signal = surprise_signal = tension_signal = reaction_signal = 0.0
        payoff_signal = question_signal = 0.0

    dialogue_density = dialogue_turn_density(events, duration) if events else min(1.0, char_rate / 20.0)
    qa_score = question_answer_score(events)
    reaction_score = reaction_shift_score(events) if events else 0.0
    payoff_score = payoff_end_weight(events) if events else 0.0
    entity_score = entity_consistency(events) if events else 0.0
    clarity_score = standalone_clarity(events, speech_coverage)
    hook_score = hookability(events) if events else min(1.0, question_signal + surprise_signal)
    cut_density_score = min(1.0, cuts_inside / max(1.0, duration / 8.0))

    normalized_total = min(
        1.0,
        speech_coverage * 0.18
        + dialogue_density * 0.12
        + qa_score * 0.12
        + reaction_score * 0.12
        + payoff_score * 0.1
        + entity_score * 0.08
        + clarity_score * 0.12
        + hook_score * 0.1
        + max(comedy_signal, emotion_signal, surprise_signal, tension_signal, reaction_signal) * 0.1
        + cut_density_score * 0.06,
    )
    total_score = round(max(1.0, normalized_total * 10.0), 2)
    ranking_focus = dominant_focus(events)

    return ScoredWindow(
        start_time=round(seed.start_time, 3),
        end_time=round(seed.end_time, 3),
        total_score=total_score,
        scores_json={
            "total_score": total_score,
            "hookability_score": round(hook_score * 10.0, 2),
            "standalone_clarity_score": round(clarity_score * 10.0, 2),
            "dialogue_turn_density": round(dialogue_density, 3),
            "question_answer_score": round(qa_score, 3),
            "reaction_shift_score": round(reaction_score, 3),
            "payoff_end_weight": round(payoff_score, 3),
            "entity_consistency": round(entity_score, 3),
            "comedy_signal": round(comedy_signal, 3),
            "emotion_signal": round(emotion_signal, 3),
            "surprise_signal": round(surprise_signal, 3),
            "tension_signal": round(tension_signal, 3),
            "reaction_signal": round(reaction_signal, 3),
            "payoff_signal": round(payoff_signal, 3),
            "speech_coverage": round(speech_coverage, 3),
            "chars_per_sec": round(char_rate, 2),
            "cuts_inside": float(cuts_inside),
        },
        title_hint=_title_from_segments(segments, seed.start_time, seed.end_time),
        metadata_json={
            "generated_by": "structure_heuristic_v1",
            "window_reason": seed.window_reason,
            "window_duration_sec": round(duration, 3),
            "speech_coverage": round(speech_coverage, 4),
            "char_count": char_count,
            "cut_count": cuts_inside,
            "transcript_excerpt": excerpt,
            "dedupe_tokens": tokens[:16],
            "language_hint": detect_language_hint(excerpt),
            "dominant_entities": all_entities,
            "source_events": [serialize_event(event) for event in events],
            "dialogue_turn_density": round(dialogue_density, 4),
            "question_answer_score": round(qa_score, 4),
            "reaction_shift_score": round(reaction_score, 4),
            "payoff_end_weight": round(payoff_score, 4),
            "entity_consistency": round(entity_score, 4),
            "standalone_clarity": round(clarity_score, 4),
            "hookability": round(hook_score, 4),
            "comedy_signal": round(comedy_signal, 4),
            "emotion_signal": round(emotion_signal, 4),
            "surprise_signal": round(surprise_signal, 4),
            "tension_signal": round(tension_signal, 4),
            "reaction_signal": round(reaction_signal, 4),
            "payoff_signal": round(payoff_signal, 4),
            "question_signal": round(question_signal, 4),
            "ranking_focus": ranking_focus,
        },
    )


def _nms(windows: list[ScoredWindow]) -> list[ScoredWindow]:
    return dedupe_scored_windows(windows, limit=MAX_CANDIDATES)


def build_candidates_for_episode(db: Session, episode_id: str) -> list[ScoredWindow]:
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise ValueError("Episode not found")

    shots = list(
        db.scalars(
            select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.shot_index.asc())
        )
    )
    segments = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.episode_id == episode_id)
            .order_by(TranscriptSegment.start_time.asc())
        )
    )

    timeline_end = _episode_timeline_end(episode, shots, segments)
    seeds = _enumerate_windows(timeline_end, segments, shots)
    scored = [
        window
        for seed in seeds
        if (window := score_window(seed, segments, shots)) is not None
    ]

    if not scored and timeline_end < MIN_WINDOW_SEC:
        excerpt = _excerpt_from_segments(segments, 0.0, timeline_end)
        scored.append(
            ScoredWindow(
                start_time=0.0,
                end_time=round(timeline_end, 3),
                total_score=6.0,
                scores_json={
                    "total_score": 6.0,
                    "hookability_score": 5.0,
                    "standalone_clarity_score": 6.0,
                    "dialogue_turn_density": 0.2,
                    "question_answer_score": 0.0,
                    "reaction_shift_score": 0.0,
                    "payoff_end_weight": 0.0,
                    "entity_consistency": 0.0,
                    "comedy_signal": 0.0,
                    "emotion_signal": 0.0,
                    "surprise_signal": 0.0,
                    "tension_signal": 0.0,
                    "reaction_signal": 0.0,
                    "payoff_signal": 0.0,
                    "speech_coverage": round(_merged_speech_coverage(segments, 0.0, timeline_end), 3),
                    "chars_per_sec": round(_chars_in_window(segments, 0.0, timeline_end) / max(timeline_end, 1.0), 2),
                    "cuts_inside": float(_cuts_inside(shots, 0.0, timeline_end)),
                },
                title_hint=_title_from_segments(segments, 0.0, timeline_end),
                metadata_json={
                    "generated_by": "structure_short_episode_fallback_v1",
                    "window_duration_sec": round(timeline_end, 3),
                    "transcript_excerpt": excerpt,
                    "dedupe_tokens": extract_tokens(excerpt)[:16],
                    "ranking_focus": "short_episode_fallback",
                    "source_events": [],
                },
            )
        )

    from app.services.candidate_rerank import rerank_scored_windows

    reranked = rerank_scored_windows(scored)
    return _nms(reranked)
