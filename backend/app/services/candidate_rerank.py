from __future__ import annotations

import json
import logging
from dataclasses import replace

from app.services.candidate_generation import ScoredWindow

logger = logging.getLogger(__name__)

_ARC_JUDGE_SYSTEM_PROMPT = """\
당신은 한국 드라마 쇼츠 편집 전문가입니다.
클립 후보의 메타 정보와 대사 발췌문을 읽고 JSON으로만 응답하세요.

반환 형식 (다른 텍스트 없이 JSON만):
{
  "arc_closed": true,        // setup→payoff가 명확히 닫히는가 (bool)
  "standalone": 7,           // 앞뒤 맥락 없이 이해 가능 정도 (0~10)
  "shorts_fit": 8,           // 30~75초 쇼츠로 적합한가 (0~10)
  "adjustment": 0.3,         // 점수 조정값 (-1.0~1.0)
  "reason": "설정과 반응이 명확하게 닫히는 구조"
}

평가 기준:
- 보상: 독립 이해 가능 + 강한 감정/반응 + 시각적 훅 + 30~75초 길이
- 패널티: 맥락 의존적 + 결론 없이 끊김 + 너무 길거나 너무 짧음
"""

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

    arc_continuity = float(
        meta.get("arc_continuity_score",
                  meta.get("entity_consistency",
                           scores.get("entity_consistency", 0.0)))
    )
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


def _apply_llm_adjustment(
    window: ScoredWindow,
    adjustment: float,
    payload: dict[str, object],
    *,
    provider: str,
) -> ScoredWindow:
    """LLM 판정 결과를 ScoredWindow에 반영한다."""
    delta = max(-1.0, min(1.0, float(adjustment)))
    new_total = round(max(1.0, min(10.0, window.total_score + delta)), 2)
    new_scores = dict(window.scores_json or {})
    new_scores["total_score"] = new_total
    new_scores["llm_arc_judge_delta"] = delta
    metadata = dict(window.metadata_json or {})
    metadata["llm_arc_judge_applied"] = True
    metadata["llm_arc_judge_provider"] = provider
    metadata["llm_arc_judge_arc_closed"] = bool(payload.get("arc_closed"))
    metadata["llm_arc_judge_standalone"] = float(payload.get("standalone", 0))
    metadata["llm_arc_judge_shorts_fit"] = float(payload.get("shorts_fit", 0))
    metadata["llm_arc_judge_reason"] = str(payload.get("reason", ""))[:200]
    return replace(window, total_score=new_total, scores_json=new_scores, metadata_json=metadata)


def _llm_judge_one(
    window: ScoredWindow,
    *,
    client: object,
    model: str,
) -> tuple[float, dict[str, object]]:
    """단일 윈도우를 LLM으로 판정해 (adjustment, payload)를 반환한다."""
    import openai  # type: ignore[import-untyped]

    assert isinstance(client, openai.OpenAI)

    meta = window.metadata_json or {}
    context: dict[str, object] = {
        "title_hint": window.title_hint,
        "duration_sec": round(window.end_time - window.start_time, 1),
        "heuristic_score": window.total_score,
        "window_reason": meta.get("window_reason") or meta.get("arc_reason", ""),
        "arc_form": meta.get("arc_form", ""),
        "transcript_excerpt": str(meta.get("transcript_excerpt", ""))[:600],
        "dominant_entities": meta.get("dominant_entities", []),
    }

    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _ARC_JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ],
        temperature=0.1,
        max_tokens=300,
    )
    raw = (response.choices[0].message.content or "{}").strip()
    payload: dict[str, object] = json.loads(raw)
    adjustment = float(payload.get("adjustment", 0.0))
    return adjustment, payload


def llm_arc_judge(
    windows: list[ScoredWindow],
    *,
    top_k: int = 5,
    provider: str = "noop",
) -> list[ScoredWindow]:
    """Top-K arc 후보를 LLM으로 서사 판정해 점수를 조정한다.

    provider="noop" 또는 OPENAI_API_KEY 없으면 메타데이터 플래그만 추가하고 점수는 그대로.
    provider="openai" 이고 API 키가 있으면 gpt-4.1-mini로 실제 판정.

    평가 축:
    - setup → payoff로 실제 닫히는가?
    - standalone 이해 가능성이 충분한가?
    - 30~75초 쇼츠로 적합한가?
    """
    from app.core.config import get_settings

    settings = get_settings()

    # noop 또는 API 키 없는 경우: 메타데이터 플래그만 추가
    if provider == "noop" or not settings.openai_api_key:
        result: list[ScoredWindow] = []
        for i, window in enumerate(windows):
            metadata = dict(window.metadata_json or {})
            if i < top_k:
                metadata["llm_arc_judge_applied"] = False
                metadata["llm_arc_judge_provider"] = provider
                metadata["llm_arc_judge_reason"] = (
                    "noop_placeholder" if provider == "noop" else "no_api_key"
                )
            result.append(replace(window, metadata_json=metadata))
        return result

    # 실제 LLM 판정
    try:
        import openai  # type: ignore[import-untyped]
        client = openai.OpenAI(api_key=settings.openai_api_key)
    except ImportError:
        logger.warning("openai 패키지가 없어 llm_arc_judge를 건너뜁니다.")
        return windows

    judged: list[ScoredWindow] = []
    for i, window in enumerate(windows):
        if i >= top_k:
            judged.append(window)
            continue
        try:
            adjustment, payload = _llm_judge_one(window, client=client, model=settings.llm_arc_judge_model)
            judged.append(_apply_llm_adjustment(window, adjustment, payload, provider=provider))
        except Exception as exc:  # noqa: BLE001
            logger.warning("llm_arc_judge 실패 (window %d): %s", i, exc)
            metadata = dict(window.metadata_json or {})
            metadata["llm_arc_judge_applied"] = False
            metadata["llm_arc_judge_error"] = str(exc)[:200]
            judged.append(replace(window, metadata_json=metadata))

    judged.sort(key=lambda w: -w.total_score)
    return judged


def rerank_candidates_for_episode(
    windows: list[ScoredWindow],
    *,
    provider: str = "heuristic_arc_v1",
    reason: str = "arc_quality_rerank",
) -> list[ScoredWindow]:
    from app.core.config import get_settings

    settings = get_settings()
    reranked = rerank_scored_windows(windows, provider=provider, reason=reason)

    llm_provider = "openai" if settings.llm_arc_judge_enabled else "noop"
    return llm_arc_judge(reranked, top_k=settings.llm_arc_judge_top_k, provider=llm_provider)
