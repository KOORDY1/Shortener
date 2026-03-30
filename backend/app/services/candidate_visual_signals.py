"""Track B: shot 기반 visual-impact candidate seed 생성.

대사가 적어도 시각적으로 인상적인 구간을 후보로 올리기 위한 heuristic.
Shot 데이터만으로 동작하며, transcript가 없어도 seed를 생성할 수 있다.
"""

from __future__ import annotations

import math
from typing import Sequence

from app.db.models import Shot, TranscriptSegment

MIN_VISUAL_WINDOW_SEC = 30.0
MAX_VISUAL_WINDOW_SEC = 90.0
MAX_VISUAL_SEEDS = 15
SHORT_SHOT_THRESHOLD_SEC = 2.0
REACTION_SHOT_MIN_CONSECUTIVE = 3


def _shot_durations(shots: Sequence[Shot]) -> list[float]:
    return [max(0.01, float(s.end_time) - float(s.start_time)) for s in shots]


def _mean(values: Sequence[float]) -> float:
    return sum(values) / max(len(values), 1)


def _stdev(values: Sequence[float], mean_val: float) -> float:
    if len(values) < 2:
        return 0.0
    return math.sqrt(sum((v - mean_val) ** 2 for v in values) / len(values))


def shot_duration_variance_score(shots: Sequence[Shot]) -> float:
    """구간 내 shot 길이 급변 정도 (표준편차/평균)."""
    durations = _shot_durations(shots)
    if len(durations) < 3:
        return 0.0
    mean_val = _mean(durations)
    if mean_val <= 0:
        return 0.0
    cv = _stdev(durations, mean_val) / mean_val
    return min(1.0, cv * 0.6)


def cut_density_spike_score(
    shots_in_window: Sequence[Shot],
    window_duration: float,
    episode_avg_cut_rate: float,
) -> float:
    """구간 내 cut 밀도가 에피소드 평균 대비 높은 정도."""
    if window_duration <= 0 or episode_avg_cut_rate <= 0:
        return 0.0
    local_rate = len(shots_in_window) / window_duration
    ratio = local_rate / episode_avg_cut_rate
    if ratio <= 1.0:
        return 0.0
    return min(1.0, (ratio - 1.0) * 0.5)


def low_speech_high_activity_score(
    speech_coverage: float,
    cut_density: float,
) -> float:
    """speech_coverage 낮은데 cut_density 높은 구간."""
    if speech_coverage >= 0.5:
        return 0.0
    speech_deficit = max(0.0, 0.5 - speech_coverage)
    return min(1.0, speech_deficit * cut_density * 3.0)


def reaction_shot_pattern_score(shots: Sequence[Shot]) -> float:
    """짧은 shot(< 2초)이 연속 3개 이상인 패턴."""
    if len(shots) < REACTION_SHOT_MIN_CONSECUTIVE:
        return 0.0
    durations = _shot_durations(shots)
    max_run = 0
    current_run = 0
    for d in durations:
        if d < SHORT_SHOT_THRESHOLD_SEC:
            current_run += 1
            max_run = max(max_run, current_run)
        else:
            current_run = 0
    if max_run < REACTION_SHOT_MIN_CONSECUTIVE:
        return 0.0
    return min(1.0, (max_run - 2) * 0.25)


def compute_visual_impact(
    shots_in_window: Sequence[Shot],
    window_duration: float,
    episode_avg_cut_rate: float,
    speech_coverage: float,
) -> float:
    """단일 구간의 종합 visual impact (0~1)."""
    variance = shot_duration_variance_score(shots_in_window)
    density = cut_density_spike_score(shots_in_window, window_duration, episode_avg_cut_rate)
    low_speech = low_speech_high_activity_score(
        speech_coverage,
        len(shots_in_window) / max(window_duration, 0.01),
    )
    reaction_pattern = reaction_shot_pattern_score(shots_in_window)
    return min(
        1.0,
        variance * 0.25 + density * 0.3 + low_speech * 0.25 + reaction_pattern * 0.2,
    )


def _shots_in_range(shots: Sequence[Shot], start: float, end: float) -> list[Shot]:
    return [
        s for s in shots
        if float(s.start_time) < end and float(s.end_time) > start
    ]


def _speech_coverage_in_range(
    segments: Sequence[TranscriptSegment], start: float, end: float,
) -> float:
    duration = end - start
    if duration <= 0:
        return 0.0
    covered = 0.0
    for seg in segments:
        lo = max(float(seg.start_time), start)
        hi = min(float(seg.end_time), end)
        if hi > lo:
            covered += hi - lo
    return min(1.0, covered / duration)


def generate_visual_seeds(
    shots: Sequence[Shot],
    segments: Sequence[TranscriptSegment],
    timeline_end: float,
) -> list[dict]:
    """Visual-impact track에서 WindowSeed 호환 dict 목록을 반환한다."""
    if len(shots) < 4:
        return []

    episode_avg_cut_rate = len(shots) / max(timeline_end, 1.0)
    seeds: list[dict] = []
    seen: set[tuple[int, int]] = set()

    for start_idx in range(len(shots)):
        for end_idx in range(start_idx + 3, min(len(shots), start_idx + 25)):
            start_time = float(shots[start_idx].start_time)
            end_time = float(shots[end_idx].end_time)
            duration = end_time - start_time
            if duration < MIN_VISUAL_WINDOW_SEC or duration > MAX_VISUAL_WINDOW_SEC:
                continue
            key = (int(round(start_time * 10)), int(round(end_time * 10)))
            if key in seen:
                continue
            seen.add(key)

            window_shots = shots[start_idx : end_idx + 1]
            speech_cov = _speech_coverage_in_range(segments, start_time, end_time)
            impact = compute_visual_impact(
                window_shots, duration, episode_avg_cut_rate, speech_cov,
            )
            if impact < 0.15:
                continue

            seeds.append({
                "start_time": round(start_time, 3),
                "end_time": round(end_time, 3),
                "window_reason": "visual_impact",
                "candidate_track": "visual",
                "visual_impact_score": round(impact, 3),
                "speech_coverage": round(speech_cov, 3),
                "shot_count": len(window_shots),
            })

    seeds.sort(key=lambda s: s["visual_impact_score"], reverse=True)
    return seeds[:MAX_VISUAL_SEEDS]
