"""
쇼츠 후보 구간을 에피소드 자막·샷 경계·재생 길이로부터 휴리스틱 생성합니다.
ML 없이 규칙 기반이며, 자막이 없을 때는 시간 슬라이딩으로 보조합니다.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Episode, Shot, TranscriptSegment

# 쇼츠에 맞는 구간 길이(초)
MIN_WINDOW_SEC = 10.0
MAX_WINDOW_SEC = 180.0
OPTIMAL_DURATION_SEC = 28.0
DURATION_SIGMA_SEC = 14.0

MAX_CANDIDATES = 14
SLIDE_STEP_SEC = 4.0
NMS_IOU_THRESHOLD = 0.42
TEXT_DEDUPE_JACCARD_THRESHOLD = 0.72
TEXT_DEDUPE_MAX_START_GAP_SEC = 24.0
TEXT_DEDUPE_MIN_OVERLAP_SEC = 6.0
LONG_CANDIDATE_MIN_SEC = 60.0
MIN_LONG_CANDIDATES = 3

COMEDY_KEYWORDS = (
    "웃",
    "웃기",
    "웃겨",
    "농담",
    "장난",
    "유머",
    "재밌",
    "코미디",
    "하하",
    "ㅋㅋ",
    "미친",
    "황당",
    "바보",
    "말도 안",
)
EMOTION_KEYWORDS = (
    "감동",
    "눈물",
    "울",
    "울컥",
    "미안",
    "고마",
    "사랑",
    "마음",
    "아프",
    "슬프",
    "그리",
    "후회",
    "용서",
    "가족",
    "엄마",
    "아빠",
    "죽",
    "이별",
)
TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")


@dataclass
class ScoredWindow:
    start_time: float
    end_time: float
    total_score: float
    scores_json: dict[str, float]
    title_hint: str
    metadata_json: dict


def _episode_timeline_end(
    episode: Episode, shots: Sequence[Shot], segments: Sequence[TranscriptSegment]
) -> float:
    t = float(episode.duration_seconds or 0.0)
    if shots:
        t = max(t, max(s.end_time for s in shots))
    if segments:
        t = max(t, max(s.end_time for s in segments))
    return max(t, 30.0)


def _merged_speech_coverage(segments: Sequence[TranscriptSegment], a: float, b: float) -> float:
    """[a,b] 안에서 자막이 덮는 시간 비율 (겹치는 구간은 병합)."""
    dur = b - a
    if dur <= 0:
        return 0.0
    intervals: list[tuple[float, float]] = []
    for s in segments:
        lo = max(float(s.start_time), a)
        hi = min(float(s.end_time), b)
        if hi > lo:
            intervals.append((lo, hi))
    if not intervals:
        return 0.0
    intervals.sort()
    merged_len = 0.0
    cur_lo, cur_hi = intervals[0]
    for lo, hi in intervals[1:]:
        if lo <= cur_hi:
            cur_hi = max(cur_hi, hi)
        else:
            merged_len += cur_hi - cur_lo
            cur_lo, cur_hi = lo, hi
    merged_len += cur_hi - cur_lo
    return min(1.0, merged_len / dur)


def _cuts_inside(shots: Sequence[Shot], a: float, b: float) -> int:
    """구간 내부에서 샷이 바뀌는 횟수(샷 시작점이 (a,b) 안에 있는 경우)."""
    n = 0
    for s in shots:
        st = float(s.start_time)
        if st > a + 0.05 and st < b - 0.05:
            n += 1
    return n


def _chars_in_window(segments: Sequence[TranscriptSegment], a: float, b: float) -> int:
    n = 0
    for s in segments:
        lo = max(float(s.start_time), a)
        hi = min(float(s.end_time), b)
        if hi > lo:
            n += len((s.text or "").strip())
    return n


def _duration_shape(dur: float) -> float:
    """최적 길이 근처일수록 1에 가깝게."""
    if dur < MIN_WINDOW_SEC or dur > MAX_WINDOW_SEC:
        return 0.15
    x = (dur - OPTIMAL_DURATION_SEC) / DURATION_SIGMA_SEC
    return float(math.exp(-0.5 * x * x))


def _cuts_shape(cuts: int, dur: float) -> float:
    """너무 적거나 많은 컷은 쇼츠 후보로 덜 유리."""
    rate = cuts / max(dur / 10.0, 0.5)
    if rate < 0.15:
        return 0.35 + 0.4 * (rate / 0.15)
    if rate > 1.8:
        return max(0.25, 1.0 - (rate - 1.8) * 0.35)
    return 0.75 + 0.25 * math.sin(min(rate, 1.5) * math.pi / 2)


def _title_from_segments(segments: Sequence[TranscriptSegment], a: float, b: float) -> str:
    parts: list[str] = []
    for s in segments:
        if float(s.end_time) <= a or float(s.start_time) >= b:
            continue
        t = (s.text or "").strip().replace("\n", " ")
        if t:
            parts.append(t)
    if not parts:
        return f"구간 {a:.1f}–{b:.1f}s"
    hint = " · ".join(parts[:3])
    if len(hint) > 200:
        hint = hint[:197] + "…"
    return hint


def _excerpt_from_segments(
    segments: Sequence[TranscriptSegment], a: float, b: float, max_chars: int = 260
) -> str:
    parts: list[str] = []
    total = 0
    for s in segments:
        if float(s.end_time) <= a or float(s.start_time) >= b:
            continue
        text = (s.text or "").strip().replace("\n", " ")
        if not text:
            continue
        parts.append(text)
        total += len(text) + 1
        if total >= max_chars:
            break
    return " ".join(parts)[:max_chars]


def _normalized_text(value: str) -> str:
    cleaned = value.lower().replace("\n", " ")
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"[^0-9a-z가-힣 ]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _text_tokens(value: str) -> list[str]:
    text = _normalized_text(value)
    if not text:
        return []
    tokens = [token for token in TOKEN_RE.findall(text) if len(token) >= 2]
    seen: set[str] = set()
    out: list[str] = []
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _keyword_signal_score(text: str, keywords: tuple[str, ...]) -> float:
    normalized = _normalized_text(text)
    if not normalized:
        return 0.0
    hits = sum(1 for keyword in keywords if keyword in normalized)
    punctuation_bonus = 0.0
    if "!" in text:
        punctuation_bonus += 0.15
    if "?" in text:
        punctuation_bonus += 0.1
    return min(1.0, hits * 0.22 + punctuation_bonus)


def _jaccard_similarity(left: Sequence[str], right: Sequence[str]) -> float:
    if not left or not right:
        return 0.0
    a = set(left)
    b = set(right)
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _is_text_near_duplicate(candidate: ScoredWindow, kept: ScoredWindow) -> bool:
    cand_text = str(candidate.metadata_json.get("transcript_excerpt") or candidate.title_hint)
    kept_text = str(kept.metadata_json.get("transcript_excerpt") or kept.title_hint)
    cand_tokens = candidate.metadata_json.get("dedupe_tokens") or _text_tokens(cand_text)
    kept_tokens = kept.metadata_json.get("dedupe_tokens") or _text_tokens(kept_text)
    similarity = _jaccard_similarity(cand_tokens, kept_tokens)
    if similarity < TEXT_DEDUPE_JACCARD_THRESHOLD:
        return False
    overlap = max(
        0.0, min(candidate.end_time, kept.end_time) - max(candidate.start_time, kept.start_time)
    )
    start_gap = abs(candidate.start_time - kept.start_time)
    return overlap >= TEXT_DEDUPE_MIN_OVERLAP_SEC or start_gap <= TEXT_DEDUPE_MAX_START_GAP_SEC


def _is_duplicate_candidate(candidate: ScoredWindow, kept: Sequence[ScoredWindow]) -> bool:
    if any(
        _iou_time(candidate.start_time, candidate.end_time, item.start_time, item.end_time)
        >= NMS_IOU_THRESHOLD
        for item in kept
    ):
        return True
    return any(_is_text_near_duplicate(candidate, item) for item in kept)


def _window_duration(window: ScoredWindow) -> float:
    return max(0.0, float(window.end_time) - float(window.start_time))


def dedupe_scored_windows(
    windows: list[ScoredWindow], limit: int = MAX_CANDIDATES
) -> list[ScoredWindow]:
    ordered = sorted(windows, key=lambda w: -w.total_score)
    kept: list[ScoredWindow] = []
    long_candidates = [
        window for window in ordered if _window_duration(window) >= LONG_CANDIDATE_MIN_SEC
    ]

    for window in long_candidates:
        if _is_duplicate_candidate(window, kept):
            continue
        kept.append(window)
        if len(kept) >= min(limit, MIN_LONG_CANDIDATES):
            break

    for window in ordered:
        if _is_duplicate_candidate(window, kept):
            continue
        kept.append(window)
        if len(kept) >= limit:
            break

    return kept


def score_window(
    a: float,
    b: float,
    segments: Sequence[TranscriptSegment],
    shots: Sequence[Shot],
) -> ScoredWindow | None:
    dur = b - a
    if dur < MIN_WINDOW_SEC or dur > MAX_WINDOW_SEC:
        return None

    speech = _merged_speech_coverage(segments, a, b)
    chars = _chars_in_window(segments, a, b)
    char_rate = chars / max(dur, 1.0)
    cuts = _cuts_inside(shots, a, b)
    excerpt = _excerpt_from_segments(segments, a, b)
    comedy_signal = _keyword_signal_score(excerpt, COMEDY_KEYWORDS)
    emotion_signal = _keyword_signal_score(excerpt, EMOTION_KEYWORDS)
    tone_signal = max(comedy_signal, emotion_signal)

    d_shape = _duration_shape(dur)
    c_shape = _cuts_shape(cuts, dur)
    speech_component = 4.2 * speech
    char_component = 1.8 * min(1.0, char_rate / 45.0)
    dur_component = 2.5 * d_shape
    cut_component = 1.5 * c_shape
    tone_component = 1.65 * tone_signal

    raw = speech_component + char_component + dur_component + cut_component + tone_component
    total = round(min(10.0, max(1.0, raw)), 2)

    hook = round(min(10.0, total + 0.15 * c_shape + 0.1 * speech + 0.25 * tone_signal), 2)
    clarity = round(min(10.0, total - 0.2 * (1.0 - speech)), 2)
    commentary = round(min(10.0, total + 0.12 * speech + 0.18 * tone_signal), 2)
    comedy_score = round(min(10.0, total * 0.72 + comedy_signal * 3.1), 2)
    emotion_score = round(min(10.0, total * 0.72 + emotion_signal * 3.1), 2)
    dedupe_tokens = _text_tokens(excerpt or _title_from_segments(segments, a, b))[:12]

    return ScoredWindow(
        start_time=round(a, 3),
        end_time=round(b, 3),
        total_score=total,
        scores_json={
            "total_score": total,
            "hook_score": hook,
            "clarity_score": clarity,
            "commentary_score": commentary,
            "comedy_score": comedy_score,
            "emotion_score": emotion_score,
            "speech_coverage": round(speech, 3),
            "chars_per_sec": round(char_rate, 2),
            "cuts_inside": float(cuts),
        },
        title_hint=_title_from_segments(segments, a, b),
        metadata_json={
            "generated_by": "heuristic_v2",
            "speech_coverage": round(speech, 4),
            "cut_count": cuts,
            "char_count": chars,
            "window_duration_sec": round(dur, 3),
            "transcript_excerpt": excerpt,
            "dedupe_tokens": dedupe_tokens,
            "comedy_signal": round(comedy_signal, 3),
            "emotion_signal": round(emotion_signal, 3),
            "ranking_focus": "comedy_or_emotion",
        },
    )


def _enumerate_windows(
    t_end: float,
    segments: list[TranscriptSegment],
    shots: list[Shot],
) -> list[tuple[float, float]]:
    seen: set[tuple[int, int]] = set()
    out: list[tuple[float, float]] = []

    def add(a: float, b: float) -> None:
        a = max(0.0, float(a))
        b = min(float(t_end), float(b))
        if b - a < MIN_WINDOW_SEC:
            return
        key = (int(round(a * 100)), int(round(b * 100)))
        if key in seen:
            return
        seen.add(key)
        out.append((a, b))

    target_durs = [16.0, 22.0, 28.0, 34.0, 42.0, 52.0, 64.0, 80.0, 100.0, 130.0, 160.0, 180.0]
    t = 0.0
    while t < t_end - MIN_WINDOW_SEC + 1e-6:
        for d in target_durs:
            if t + d <= t_end + 1e-6:
                add(t, t + d)
        t += SLIDE_STEP_SEC

    if segments:
        n = len(segments)
        for i in range(n):
            t0 = float(segments[i].start_time)
            t1 = float(segments[i].end_time)
            j = i
            while j + 1 < n and float(segments[j + 1].end_time) - t0 <= MAX_WINDOW_SEC:
                j += 1
                t1 = float(segments[j].end_time)
                if t1 - t0 >= MIN_WINDOW_SEC:
                    add(t0, t1)
            for k in range(max(0, i - 12), i):
                t0b = float(segments[k].start_time)
                if t1 - t0b <= MAX_WINDOW_SEC and t1 - t0b >= MIN_WINDOW_SEC:
                    add(t0b, t1)

    if shots:
        for si, shot in enumerate(shots):
            t0 = float(shot.start_time)
            acc_end = float(shot.end_time)
            j = si
            while j < len(shots) and acc_end - t0 <= MAX_WINDOW_SEC:
                if acc_end - t0 >= MIN_WINDOW_SEC:
                    add(t0, acc_end)
                j += 1
                if j < len(shots):
                    acc_end = float(shots[j].end_time)

    return out


def _iou_time(a0: float, a1: float, b0: float, b1: float) -> float:
    inter = max(0.0, min(a1, b1) - max(a0, b0))
    if inter <= 0:
        return 0.0
    union = max(a1, b1) - min(a0, b0)
    return inter / union if union > 0 else 0.0


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

    t_end = _episode_timeline_end(episode, shots, segments)
    raw_pairs = _enumerate_windows(t_end, segments, shots)

    scored: list[ScoredWindow] = []
    for a, b in raw_pairs:
        sw = score_window(a, b, segments, shots)
        if sw is not None:
            scored.append(sw)

    if not scored:
        mid = min(OPTIMAL_DURATION_SEC, max(MIN_WINDOW_SEC, t_end * 0.35))
        fallback = score_window(0.0, min(mid, t_end), segments, shots)
        if fallback:
            scored.append(fallback)

    return _nms(scored)
