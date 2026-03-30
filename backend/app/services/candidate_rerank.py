from __future__ import annotations

from dataclasses import replace

from app.services.candidate_generation import ScoredWindow

LENGTH_FIT_IDEAL_MIN = 30.0
LENGTH_FIT_IDEAL_MAX = 75.0


def _evaluate_arc_quality(window: ScoredWindow) -> dict[str, float]:
    """서사 아크 완성도를 평가해 arc_quality_delta와 세부 축을 반환한다."""
    meta = window.metadata_json or {}
    scores = window.scores_json or {}
    source_events = meta.get("source_events") or []

    setup_strength = 0.0
    payoff_strength = 0.0
    if source_events:
        first_ev = source_events[0] if isinstance(source_events[0], dict) else {}
        last_ev = source_events[-1] if isinstance(source_events[-1], dict) else {}
        setup_strength = float(first_ev.get("setup_score", 0.0))
        payoff_strength = float(last_ev.get("payoff_score", 0.0))

    setup_to_payoff_delta = max(0.0, payoff_strength - setup_strength * 0.5)

    arc_continuity = float(meta.get("entity_consistency", scores.get("entity_consistency", 0.0)))
    standalone = float(meta.get("standalone_clarity", scores.get("standalone_clarity_score", 0.0)) or 0.0)
    if standalone > 1.0:
        standalone = standalone / 10.0

    visual_impact = float(meta.get("visual_impact", scores.get("visual_impact", 0.0)))
    audio_impact = float(meta.get("audio_impact", scores.get("audio_impact", 0.0)))
    visual_audio_impact = min(1.0, visual_impact * 0.6 + audio_impact * 0.4)

    avg_ctx_dep = 0.0
    if source_events:
        ctx_deps = [float(e.get("context_dependency_score", 0.0)) for e in source_events if isinstance(e, dict)]
        avg_ctx_dep = sum(ctx_deps) / max(len(ctx_deps), 1)
    context_penalty = max(0.0, avg_ctx_dep - 0.35) * 0.6

    duration = float(meta.get("window_duration_sec", 0.0))
    if duration <= 0:
        duration = window.end_time - window.start_time
    if LENGTH_FIT_IDEAL_MIN <= duration <= LENGTH_FIT_IDEAL_MAX:
        length_fit = 1.0
    elif duration < LENGTH_FIT_IDEAL_MIN:
        length_fit = max(0.3, duration / LENGTH_FIT_IDEAL_MIN)
    else:
        length_fit = max(0.3, 1.0 - (duration - LENGTH_FIT_IDEAL_MAX) / 120.0)

    payoff_weakness_penalty = 0.0
    if payoff_strength < 0.15 and setup_strength >= 0.2:
        payoff_weakness_penalty = 0.15

    arc_quality = (
        setup_strength * 0.15
        + payoff_strength * 0.25
        + setup_to_payoff_delta * 0.15
        + arc_continuity * 0.10
        + standalone * 0.15
        + visual_audio_impact * 0.05
        + length_fit * 0.05
        - context_penalty
        - payoff_weakness_penalty
    )
    arc_quality_delta = round(max(-1.5, min(1.5, (arc_quality - 0.3) * 3.0)), 3)

    winning = []
    if payoff_strength >= 0.3:
        winning.append("strong_payoff")
    if setup_to_payoff_delta >= 0.2:
        winning.append("payoff_exceeds_setup")
    if visual_audio_impact >= 0.3:
        winning.append("visual_audio_impact")
    if standalone >= 0.5:
        winning.append("standalone_clarity")
    if arc_continuity >= 0.3:
        winning.append("entity_continuity")

    return {
        "arc_quality_delta": arc_quality_delta,
        "setup_strength": round(setup_strength, 3),
        "payoff_strength": round(payoff_strength, 3),
        "setup_to_payoff_delta": round(setup_to_payoff_delta, 3),
        "arc_continuity": round(arc_continuity, 3),
        "standalone_understandability": round(standalone, 3),
        "visual_audio_impact": round(visual_audio_impact, 3),
        "context_penalty": round(context_penalty, 3),
        "length_fit": round(length_fit, 3),
        "winning_signals": winning,
    }


def rerank_scored_windows(
    windows: list[ScoredWindow],
    *,
    provider: str = "heuristic_arc_v1",
    reason: str = "arc_quality_rerank",
) -> list[ScoredWindow]:
    reranked: list[ScoredWindow] = []
    for window in windows:
        arc_eval = _evaluate_arc_quality(window)
        delta = arc_eval["arc_quality_delta"]

        new_total = round(max(1.0, min(10.0, window.total_score + delta)), 2)
        new_scores = dict(window.scores_json or {})
        new_scores["total_score"] = new_total
        new_scores["arc_quality_delta"] = delta

        metadata = dict(window.metadata_json or {})
        metadata["rerank_applied"] = True
        metadata["rerank_provider"] = provider
        metadata["rerank_reason"] = reason
        metadata["arc_reason"] = metadata.get("arc_reason") or metadata.get("window_reason", "")
        metadata["winning_signals"] = arc_eval["winning_signals"]
        metadata["setup_strength"] = arc_eval["setup_strength"]
        metadata["payoff_strength"] = arc_eval["payoff_strength"]
        metadata["setup_to_payoff_delta"] = arc_eval["setup_to_payoff_delta"]
        metadata["arc_continuity"] = arc_eval["arc_continuity"]
        metadata["standalone_understandability"] = arc_eval["standalone_understandability"]
        metadata["visual_audio_impact_score"] = arc_eval["visual_audio_impact"]
        metadata["context_penalty"] = arc_eval["context_penalty"]
        metadata["length_fit"] = arc_eval["length_fit"]

        reranked.append(replace(
            window,
            total_score=new_total,
            scores_json=new_scores,
            metadata_json=metadata,
        ))

    reranked.sort(key=lambda w: -w.total_score)
    return reranked


def llm_arc_judge(
    windows: list[ScoredWindow],
    *,
    top_k: int = 5,
    provider: str = "noop",
) -> list[ScoredWindow]:
    """Top-K arc 후보를 대상으로 LLM 서사 판정을 수행한다.

    현재는 noop 구현. 향후 LLM을 "생성기"가 아니라 "서사 판정기"로 연결한다.

    평가 축 (향후 구현 시):
    - 이 후보가 실제로 setup → payoff로 닫히는가?
    - standalone 이해 가능성이 충분한가?
    - 30~75초 쇼츠로 먹히는가?
    - 대사가 적어도 화면/오디오 임팩트만으로 강한가?
    """
    result: list[ScoredWindow] = []
    for i, window in enumerate(windows):
        metadata = dict(window.metadata_json or {})
        if i < top_k:
            metadata["llm_arc_judge_applied"] = (provider != "noop")
            metadata["llm_arc_judge_provider"] = provider
            metadata["llm_arc_judge_reason"] = (
                "noop_placeholder" if provider == "noop"
                else f"judged_by_{provider}"
            )
        result.append(replace(window, metadata_json=metadata))
    return result


def rerank_candidates_for_episode(
    windows: list[ScoredWindow],
    *,
    provider: str = "heuristic_arc_v1",
    reason: str = "arc_quality_rerank",
) -> list[ScoredWindow]:
    reranked = rerank_scored_windows(windows, provider=provider, reason=reason)
    return llm_arc_judge(reranked, provider="noop")
