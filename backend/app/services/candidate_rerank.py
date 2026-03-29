from __future__ import annotations

from dataclasses import replace

from app.services.candidate_generation import ScoredWindow


def rerank_scored_windows(
    windows: list[ScoredWindow],
    *,
    provider: str = "heuristic_noop",
    reason: str = "no_external_rerank",
) -> list[ScoredWindow]:
    reranked: list[ScoredWindow] = []
    for window in windows:
        metadata = dict(window.metadata_json or {})
        metadata.setdefault("rerank_applied", False)
        metadata.setdefault("rerank_provider", provider)
        metadata.setdefault("rerank_reason", reason)
        reranked.append(replace(window, metadata_json=metadata))
    return reranked


def rerank_candidates_for_episode(
    windows: list[ScoredWindow],
    *,
    provider: str = "heuristic_noop",
    reason: str = "no_external_rerank",
) -> list[ScoredWindow]:
    return rerank_scored_windows(windows, provider=provider, reason=reason)
