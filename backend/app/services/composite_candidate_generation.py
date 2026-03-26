from __future__ import annotations

from app.services.candidate_generation import ScoredWindow

MAX_COMPOSITE_CANDIDATES = 4
MAX_COMPOSITE_INPUTS = 14
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


def build_composite_candidates(windows: list[ScoredWindow]) -> list[ScoredWindow]:
    ordered = sorted(windows, key=lambda item: item.total_score, reverse=True)[:MAX_COMPOSITE_INPUTS]
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
            right_focus = str(right.metadata_json.get("ranking_focus") or "")
            same_focus = left_focus == right_focus and bool(left_focus)
            if overlap_score < 0.04 and not same_focus:
                continue

            gap_bonus = 0.35 if gap <= 45 else 0.18 if gap <= 120 else 0.0
            duration_penalty = 0.0 if total_duration <= 50 else min(0.45, (total_duration - 50) / 30.0)
            total_score = round(
                min(
                    10.0,
                    ((left.total_score + right.total_score) / 2.0)
                    + overlap_score * 0.9
                    + (0.35 if same_focus else 0.0)
                    + gap_bonus
                    - min(0.45, gap / 360.0)
                    - duration_penalty,
                ),
                2,
            )
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
                        "role": "setup",
                    },
                    {
                        "start_time": round(right.start_time, 3),
                        "end_time": round(right.end_time, 3),
                        "order": 1,
                        "role": "payoff",
                    },
                ],
                "transcript_excerpt": excerpt,
                "dedupe_tokens": sorted(left_tokens | right_tokens)[:16],
                "ranking_focus": left_focus or right_focus or "composite",
                "composite_similarity": round(overlap_score, 3),
                "span_gap_sec": round(gap, 3),
            }
            scores = {
                **(left.scores_json or {}),
                "total_score": total_score,
                "composite_similarity": round(overlap_score, 3),
                "span_gap_sec": round(gap, 3),
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
