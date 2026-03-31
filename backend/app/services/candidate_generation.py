"""내용 구조 중심 contiguous 후보 생성기 (multi-track)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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
    EmbeddingSignals,
    compute_embedding_signals,
    detect_language_hint,
    dominant_entities,
    extract_token_stream,
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
from app.services.candidate_visual_signals import compute_visual_impact, generate_visual_seeds
from app.services.candidate_audio_signals import generate_audio_seeds_live
from app.core.config import get_settings

MAX_CANDIDATES = 14
NMS_IOU_THRESHOLD = 0.52
TEXT_DEDUPE_JACCARD_THRESHOLD = 0.82
TEXT_DEDUPE_MAX_START_GAP_SEC = 20.0
TEXT_DEDUPE_MIN_OVERLAP_SEC = 8.0


@dataclass(frozen=True)
class LengthPolicy:
    """길이 정책 3계층 분리.

    - search window: micro-event 기반 후보 탐색 범위
    - core span total: 복합 후보의 코어 스팬 합산 상한
    - render target: 실제 출력 쇼츠 목표 길이 (권장)
    """

    # 탐색 윈도우 (search window)
    min_window_sec: float = 30.0
    max_window_sec: float = 180.0

    # 코어 아크 합산 (core span total)
    max_2span_sec: float = 64.0
    max_3span_sec: float = 90.0

    # 최종 렌더 타깃 (render target)
    render_target_min_sec: float = 30.0
    render_target_max_sec: float = 75.0
    render_ideal_sec: float = 50.0

    @classmethod
    def from_settings(cls) -> "LengthPolicy":
        settings = get_settings()
        return cls(
            min_window_sec=settings.length_min_window_sec,
            max_window_sec=settings.length_max_window_sec,
            max_2span_sec=settings.length_max_2span_sec,
            max_3span_sec=settings.length_max_3span_sec,
            render_target_min_sec=settings.length_render_target_min_sec,
            render_target_max_sec=settings.length_render_target_max_sec,
            render_ideal_sec=settings.length_render_ideal_sec,
        )


_DEFAULT_LENGTH_POLICY = LengthPolicy()

# 하위 호환 별칭 — 기존 코드에서 사용하는 모듈 수준 상수
MIN_WINDOW_SEC = _DEFAULT_LENGTH_POLICY.min_window_sec
MAX_WINDOW_SEC = _DEFAULT_LENGTH_POLICY.max_window_sec


@dataclass
class ScoringWeights:
    """스코어링 가중치 프로파일. A/B 테스트나 실험 시 교체 가능."""

    speech_coverage: float = 0.12
    dialogue_density: float = 0.10
    qa_score: float = 0.12
    reaction_score: float = 0.12
    payoff_score: float = 0.14
    entity_score: float = 0.06
    clarity_score: float = 0.10
    hook_score: float = 0.10
    tone_signal: float = 0.06
    cut_density: float = 0.03
    visual_audio_bonus: float = 0.05

    @classmethod
    def from_profile(cls, profile: str) -> "ScoringWeights":
        """설정된 프로파일 이름으로 가중치를 반환한다."""
        if profile == "reaction_heavy":
            return cls(reaction_score=0.20, payoff_score=0.16, qa_score=0.10,
                       speech_coverage=0.10, hook_score=0.08)
        if profile == "payoff_heavy":
            return cls(payoff_score=0.22, qa_score=0.14, reaction_score=0.10,
                       hook_score=0.08, speech_coverage=0.10)
        return cls()  # default


_DEFAULT_WEIGHTS = ScoringWeights()


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


def _diversity_penalty(candidate: ScoredWindow, kept: list[ScoredWindow]) -> float:
    """인물·사건·payoff 유형 중복 시 diversity penalty를 반환한다.

    kept에 이미 선택된 후보들과 candidate의 entity, window_reason,
    ranking_focus 유사성을 검사해 0.0~0.25 범위 패널티를 합산한다.
    패널티가 클수록 다양성 면에서 불리하다.
    """
    if not kept:
        return 0.0

    meta = candidate.metadata_json
    cand_entities = set(meta.get("dominant_entities") or [])
    cand_reason = str(meta.get("window_reason", ""))
    cand_focus = str(meta.get("ranking_focus", ""))

    max_entity_overlap = 0.0
    reason_count = 0
    focus_count = 0

    for item in kept:
        item_meta = item.metadata_json
        # entity 겹침 (Jaccard)
        item_entities = set(item_meta.get("dominant_entities") or [])
        if cand_entities and item_entities:
            union = cand_entities | item_entities
            if union:
                overlap = len(cand_entities & item_entities) / len(union)
                max_entity_overlap = max(max_entity_overlap, overlap)

        # window_reason 중복
        if cand_reason and cand_reason == str(item_meta.get("window_reason", "")):
            reason_count += 1

        # ranking_focus 중복
        if cand_focus and cand_focus == str(item_meta.get("ranking_focus", "")):
            focus_count += 1

    penalty = 0.0
    # 인물 중복 패널티: entity Jaccard >= 0.6이면 최대 0.12
    if max_entity_overlap >= 0.6:
        penalty += min(0.12, (max_entity_overlap - 0.4) * 0.3)

    # window_reason 중복 패널티: 동일 reason이 2개 이상이면 패널티
    if reason_count >= 2:
        penalty += 0.08
    elif reason_count >= 1:
        penalty += 0.04

    # ranking_focus 중복 패널티
    if focus_count >= 2:
        penalty += 0.05

    return min(0.25, penalty)


def dedupe_scored_windows(
    windows: list[ScoredWindow],
    limit: int = MAX_CANDIDATES,
    *,
    diversity_aware: bool = True,
) -> list[ScoredWindow]:
    """중복 제거 + diversity-aware selection.

    1단계: 순수 중복 제거 (IOU + Jaccard + span 동일)
    2단계: diversity_aware=True이면 diversity penalty를 적용해 재정렬 후 선택
    """
    ordered = sorted(windows, key=lambda window: -window.total_score)

    # 1단계: 순수 중복 제거
    non_duplicates: list[ScoredWindow] = []
    for window in ordered:
        if _is_duplicate_candidate(window, non_duplicates):
            continue
        non_duplicates.append(window)

    if not diversity_aware or len(non_duplicates) <= limit:
        return non_duplicates[:limit]

    # 2단계: diversity-aware greedy selection
    kept: list[ScoredWindow] = []
    remaining = list(non_duplicates)

    while remaining and len(kept) < limit:
        best_idx = 0
        best_effective_score = -1.0

        for idx, cand in enumerate(remaining):
            penalty = _diversity_penalty(cand, kept)
            effective_score = cand.total_score * (1.0 - penalty)
            if effective_score > best_effective_score:
                best_effective_score = effective_score
                best_idx = idx

        kept.append(remaining.pop(best_idx))

    return kept


def _shot_window_fallback(
    shots: Sequence[Shot],
    timeline_end: float,
    lp: LengthPolicy | None = None,
) -> list[WindowSeed]:
    lp = lp or _DEFAULT_LENGTH_POLICY
    seeds: list[WindowSeed] = []
    for start_index, start_shot in enumerate(shots):
        for end_index in range(start_index, min(len(shots), start_index + 14)):
            end_time = float(shots[end_index].end_time)
            duration = end_time - float(start_shot.start_time)
            if duration > lp.max_window_sec:
                break
            if duration < lp.min_window_sec:
                continue
            if duration <= lp.render_target_max_sec or end_index - start_index <= 8:
                seeds.append(
                    WindowSeed(
                        start_time=round(float(start_shot.start_time), 3),
                        end_time=round(end_time, 3),
                        events=[],
                        window_reason="shot_boundary_fallback",
                    )
                )
    if not seeds and timeline_end >= lp.min_window_sec:
        seeds.append(
            WindowSeed(
                start_time=0.0,
                end_time=min(timeline_end, lp.max_window_sec),
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
    lp: LengthPolicy | None = None,
) -> list[WindowSeed]:
    lp = lp or _DEFAULT_LENGTH_POLICY
    seen: set[tuple[int, int]] = set()
    seeds: list[WindowSeed] = []
    events = build_micro_events(segments, shots)

    def add_seed(start: float, end: float, event_slice: Sequence[CandidateEvent], reason: str) -> None:
        start = max(0.0, float(start))
        end = min(float(timeline_end), float(end))
        if end - start < lp.min_window_sec or end - start > lp.max_window_sec:
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
                if duration > lp.max_window_sec:
                    break
                if duration < lp.min_window_sec:
                    continue
                reason = _event_window_reason(event_slice)
                if reason:
                    add_seed(start_time, end_time, event_slice, reason)
        if seeds:
            return seeds
    return _shot_window_fallback(shots, timeline_end, lp)


def score_window(
    seed: WindowSeed,
    segments: Sequence[TranscriptSegment],
    shots: Sequence[Shot],
    *,
    episode_avg_cut_rate: float = 0.0,
    timeline_end: float = 0.0,
    weights: ScoringWeights | None = None,
    length_policy: LengthPolicy | None = None,
) -> ScoredWindow | None:
    lp = length_policy or _DEFAULT_LENGTH_POLICY
    duration = seed.end_time - seed.start_time
    if duration < lp.min_window_sec or duration > lp.max_window_sec:
        return None

    speech_coverage = _merged_speech_coverage(segments, seed.start_time, seed.end_time)
    char_count = _chars_in_window(segments, seed.start_time, seed.end_time)
    char_rate = char_count / max(duration, 1.0)
    cuts_inside = _cuts_inside(shots, seed.start_time, seed.end_time)
    excerpt = _excerpt_from_segments(segments, seed.start_time, seed.end_time)
    tokens = extract_tokens(excerpt)
    raw_stream = extract_token_stream(excerpt)
    all_entities = dominant_entities(raw_stream, limit=8)
    events = seed.events

    candidate_track = getattr(seed, "_candidate_track", None) or "dialogue"
    track_visual_impact = getattr(seed, "_visual_impact_score", 0.0) or 0.0
    track_audio_impact = getattr(seed, "_audio_impact_score", 0.0) or 0.0

    if events:
        comedy_signal = max((event.tone_signals["comedy_signal"] for event in events), default=0.0)
        emotion_signal = max((event.tone_signals["emotion_signal"] for event in events), default=0.0)
        surprise_signal = max((event.tone_signals["surprise_signal"] for event in events), default=0.0)
        tension_signal = max((event.tone_signals["tension_signal"] for event in events), default=0.0)
        reaction_signal = max((event.tone_signals["reaction_signal"] for event in events), default=0.0)
        payoff_signal = max((event.tone_signals["payoff_signal"] for event in events), default=0.0)
        question_signal = max((event.tone_signals["question_signal"] for event in events), default=0.0)
        max_visual_impact = max((e.visual_impact_score for e in events), default=0.0)
        max_audio_impact = max((e.audio_impact_score for e in events), default=0.0)
    else:
        comedy_signal = emotion_signal = surprise_signal = tension_signal = reaction_signal = 0.0
        payoff_signal = question_signal = 0.0
        max_visual_impact = 0.0
        max_audio_impact = 0.0

    # ML 임베딩 시그널 — EMBEDDING_SIGNALS_ENABLED=true + API 키 존재 시만 활성
    _EMB_ALPHA = 0.8  # 임베딩 시그널 혼합 계수 (보수적)
    _settings = get_settings()
    emb_signals: EmbeddingSignals | None = None
    emb_attempted = False
    if _settings.embedding_signals_enabled and _settings.openai_api_key:
        emb_attempted = True
        text_for_emb = excerpt[:_settings.embedding_signals_max_chars]
        if text_for_emb.strip():
            emb_signals = compute_embedding_signals(
                text_for_emb,
                api_key=_settings.openai_api_key,
                model=_settings.embedding_signals_model,
            )

    if emb_signals is not None and emb_signals["embedding_used"]:
        comedy_signal = max(comedy_signal, emb_signals["comedy_emb"] * _EMB_ALPHA)
        emotion_signal = max(emotion_signal, emb_signals["emotion_emb"] * _EMB_ALPHA)
        tension_signal = max(tension_signal, emb_signals["tension_emb"] * _EMB_ALPHA)
        reaction_signal = max(reaction_signal, emb_signals["reaction_emb"] * _EMB_ALPHA)
        payoff_signal = max(payoff_signal, emb_signals["payoff_emb"] * _EMB_ALPHA)

    visual_impact = max(max_visual_impact, track_visual_impact)
    audio_impact = max(max_audio_impact, track_audio_impact)
    if visual_impact < 0.01 and episode_avg_cut_rate > 0:
        window_shots = [s for s in shots if float(s.start_time) < seed.end_time and float(s.end_time) > seed.start_time]
        visual_impact = compute_visual_impact(
            window_shots, duration, episode_avg_cut_rate, speech_coverage,
        )

    dialogue_density = dialogue_turn_density(events, duration) if events else min(1.0, char_rate / 20.0)
    qa_score = question_answer_score(events)
    reaction_score = reaction_shift_score(events) if events else 0.0
    payoff_score = payoff_end_weight(events) if events else 0.0
    entity_score = entity_consistency(events) if events else 0.0
    clarity_score = standalone_clarity(events, speech_coverage)
    hook_score = hookability(events) if events else min(1.0, question_signal + surprise_signal)
    cut_density_score = min(1.0, cuts_inside / max(1.0, duration / 8.0))

    visual_audio_bonus = min(
        visual_impact * 0.5 + audio_impact * 0.5,
        max(clarity_score, 0.3) * 1.2,
    )

    # contiguous arc completeness: setup→payoff가 닫히는 정도
    single_arc_complete = 0.0
    if events and len(events) >= 2:
        first_setup = events[0].setup_score
        last_payoff = events[-1].payoff_score
        single_arc_complete = min(
            1.0,
            first_setup * 0.3 + last_payoff * 0.4 + entity_score * 0.3,
        )

    contiguous_bonus = 0.0
    if single_arc_complete >= 0.25:
        contiguous_bonus = single_arc_complete * 0.08

    w = weights or _DEFAULT_WEIGHTS
    normalized_total = min(
        1.0,
        speech_coverage * w.speech_coverage
        + dialogue_density * w.dialogue_density
        + qa_score * w.qa_score
        + reaction_score * w.reaction_score
        + payoff_score * w.payoff_score
        + entity_score * w.entity_score
        + clarity_score * w.clarity_score
        + hook_score * w.hook_score
        + max(comedy_signal, emotion_signal, surprise_signal, tension_signal, reaction_signal) * w.tone_signal
        + cut_density_score * w.cut_density
        + visual_audio_bonus * w.visual_audio_bonus
        + contiguous_bonus,
    )
    total_score = round(max(1.0, normalized_total * 10.0), 2)
    ranking_focus = dominant_focus(events)

    from app.services.candidate_spans import extract_core_support_summary, pad_spans_to_minimum

    core_clip_spans: list[dict] = [{
        "start_time": round(seed.start_time, 3),
        "end_time": round(seed.end_time, 3),
        "order": 0,
        "role": "main",
    }]
    effective_timeline_end = max(timeline_end, seed.end_time)
    padded_spans, support_added = pad_spans_to_minimum(
        core_clip_spans,
        timeline_start=0.0,
        timeline_end=effective_timeline_end,
    )
    core_support = extract_core_support_summary(padded_spans)

    _embedding_used = bool(emb_signals and emb_signals["embedding_used"])
    _emb_comedy = round(emb_signals["comedy_emb"] if emb_signals else 0.0, 4)
    _emb_emotion = round(emb_signals["emotion_emb"] if emb_signals else 0.0, 4)
    _emb_tension = round(emb_signals["tension_emb"] if emb_signals else 0.0, 4)
    _emb_reaction = round(emb_signals["reaction_emb"] if emb_signals else 0.0, 4)
    _emb_payoff = round(emb_signals["payoff_emb"] if emb_signals else 0.0, 4)

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
            "visual_impact": round(visual_impact, 3),
            "audio_impact": round(audio_impact, 3),
            "single_arc_complete_score": round(single_arc_complete, 3),
            "comedy_emb": float(_emb_comedy),
            "emotion_emb": float(_emb_emotion),
            "tension_emb": float(_emb_tension),
            "reaction_emb": float(_emb_reaction),
            "payoff_emb": float(_emb_payoff),
        },
        title_hint=_title_from_segments(segments, seed.start_time, seed.end_time),
        metadata_json={
            "generated_by": "structure_heuristic_v2",
            "candidate_track": candidate_track,
            "arc_form": "contiguous",
            "single_arc_complete_score": round(single_arc_complete, 4),
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
            "clip_spans": padded_spans,
            "support_added_sec": support_added,
            **core_support,
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
            "visual_impact": round(visual_impact, 4),
            "audio_impact": round(audio_impact, 4),
            "ranking_focus": ranking_focus,
            "embedding_used": _embedding_used,
            "embedding_attempted": emb_attempted,
            "comedy_emb": _emb_comedy,
            "emotion_emb": _emb_emotion,
            "tension_emb": _emb_tension,
            "reaction_emb": _emb_reaction,
            "payoff_emb": _emb_payoff,
        },
    )


def _nms(windows: list[ScoredWindow]) -> list[ScoredWindow]:
    return dedupe_scored_windows(windows, limit=MAX_CANDIDATES)


def _resolve_audio_path(episode: Episode) -> Path | None:
    if not episode.audio_path:
        return None
    from app.core.config import get_settings
    settings = get_settings()
    raw = Path(episode.audio_path).expanduser()
    path = raw.resolve() if raw.is_absolute() else (settings.resolved_storage_root / raw).resolve()
    return path if path.is_file() else None


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
    episode_avg_cut_rate = len(shots) / max(timeline_end, 1.0)

    # 길이 정책 로드
    length_policy = LengthPolicy.from_settings()

    # Track A: dialogue-driven seeds
    dialogue_seeds = _enumerate_windows(timeline_end, segments, shots, length_policy)

    # Track B: visual-impact seeds
    visual_seed_dicts = generate_visual_seeds(shots, segments, timeline_end)
    for vsd in visual_seed_dicts:
        ws = WindowSeed(
            start_time=vsd["start_time"],
            end_time=vsd["end_time"],
            events=[],
            window_reason=vsd["window_reason"],
        )
        ws._candidate_track = "visual"  # type: ignore[attr-defined]
        ws._visual_impact_score = vsd.get("visual_impact_score", 0.0)  # type: ignore[attr-defined]
        dialogue_seeds.append(ws)

    # 설정된 scoring_profile로 가중치 로드 (Track C에서도 settings 필요)
    settings = get_settings()
    weights = ScoringWeights.from_profile(settings.scoring_profile)

    # Track C: audio-reaction seeds (ebur128 v2 기본 경로)
    audio_path = _resolve_audio_path(episode)
    audio_seed_dicts = generate_audio_seeds_live(
        audio_path,
        float(episode.duration_seconds or timeline_end),
        backend=settings.audio_analysis_backend,
        librosa_enabled=settings.audio_librosa_enabled,
    )
    for asd in audio_seed_dicts:
        ws = WindowSeed(
            start_time=asd["start_time"],
            end_time=asd["end_time"],
            events=[],
            window_reason=asd["window_reason"],
        )
        ws._candidate_track = "audio"  # type: ignore[attr-defined]
        ws._audio_impact_score = asd.get("audio_impact_score", 0.0)  # type: ignore[attr-defined]
        dialogue_seeds.append(ws)

    all_seeds = dialogue_seeds
    scored = [
        window
        for seed in all_seeds
        if (window := score_window(
            seed, segments, shots,
            episode_avg_cut_rate=episode_avg_cut_rate,
            timeline_end=timeline_end,
            weights=weights,
            length_policy=length_policy,
        )) is not None
    ]

    if not scored and timeline_end < length_policy.min_window_sec:
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
                    "candidate_track": "dialogue",
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
