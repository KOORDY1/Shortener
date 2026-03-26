"""
OpenAI로 쇼츠 후보(구간·휴리스틱 점수)를 텍스트 맥락 기준으로 미세 조정합니다.
영상 바이너리는 보내지 않고, 자막 발췌만 사용합니다 (비용·정책상 현실적).
"""

from __future__ import annotations

import json
from dataclasses import replace

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Episode, TranscriptSegment
from app.services.candidate_generation import ScoredWindow


def _strip_json_fence(raw: str) -> str:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1]
        s = s.rsplit("```", 1)[0]
    return s.strip()


def _transcript_excerpt_for_window(
    segments: list[TranscriptSegment], start: float, end: float, max_chars: int = 900
) -> str:
    parts: list[str] = []
    n = 0
    for s in segments:
        if float(s.end_time) <= start or float(s.start_time) >= end:
            continue
        line = (s.text or "").strip().replace("\n", " ")
        if not line:
            continue
        parts.append(line)
        n += len(line) + 1
        if n >= max_chars:
            break
    return " ".join(parts)[:max_chars]


def refine_candidates_with_llm(
    db: Session,
    episode: Episode,
    windows: list[ScoredWindow],
) -> list[ScoredWindow]:
    settings = get_settings()
    if not settings.openai_api_key or not settings.candidate_rerank_llm:
        return windows
    if not windows:
        return windows

    segs = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.episode_id == episode.id)
            .order_by(TranscriptSegment.start_time.asc())
        )
    )
    if not segs:
        return windows

    payload = []
    for i, w in enumerate(windows, start=1):
        payload.append(
            {
                "candidate_index": i,
                "start_sec": w.start_time,
                "end_sec": w.end_time,
                "duration_sec": round(w.end_time - w.start_time, 2),
                "heuristic_total_score": w.total_score,
                "title_hint": w.title_hint[:200],
                "transcript_excerpt": _transcript_excerpt_for_window(
                    segs, w.start_time, w.end_time
                ),
            }
        )

    client = OpenAI(api_key=settings.openai_api_key)
    try:
        resp = client.chat.completions.create(
            model=settings.openai_model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You rank drama-clip candidates for short-form commentary (Korean audience). "
                        "You only see subtitle excerpts, not video. "
                        'Return strict JSON: {"refinements":[{'
                        '"candidate_index":number,'
                        '"score_delta":number between -1.2 and 1.2,'
                        '"title_hint":string or null (short Korean hook, max 90 chars),'
                        '"note":string or null'
                        "}]}. "
                        "Prefer clips with clear tension, irony, or explainable 'why this line hits'. "
                        "Penalize empty or meaningless excerpts with negative score_delta."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "show_title": episode.show_title,
                            "episode_title": episode.episode_title,
                            "candidates": payload,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.35,
            max_tokens=2000,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(_strip_json_fence(raw))
        refinements = data.get("refinements")
        if not isinstance(refinements, list):
            return windows
        by_idx: dict[int, dict] = {}
        for item in refinements:
            if not isinstance(item, dict):
                continue
            try:
                idx = int(item.get("candidate_index", 0))
            except (TypeError, ValueError):
                continue
            if 1 <= idx <= len(windows):
                by_idx[idx] = item

        out: list[ScoredWindow] = []
        for i, w in enumerate(windows, start=1):
            adj = by_idx.get(i)
            if not adj:
                out.append(w)
                continue
            delta = adj.get("score_delta")
            try:
                d = float(delta) if delta is not None else 0.0
            except (TypeError, ValueError):
                d = 0.0
            d = max(-1.2, min(1.2, d))
            new_total = round(max(1.0, min(10.0, w.total_score + d)), 2)
            hint = adj.get("title_hint")
            new_hint = w.title_hint
            if isinstance(hint, str) and hint.strip():
                new_hint = hint.strip()[:255]
            note = adj.get("note")
            meta = {
                **w.metadata_json,
                "llm_refinement": "applied",
                "llm_score_delta": d,
            }
            if isinstance(note, str) and note.strip():
                meta["llm_note"] = note.strip()[:300]
            scores = dict(w.scores_json)
            scores["total_score"] = new_total
            scores["hook_score"] = round(
                max(1.0, min(10.0, scores.get("hook_score", new_total) + d * 0.5)), 2
            )
            out.append(
                replace(
                    w,
                    total_score=new_total,
                    title_hint=new_hint,
                    scores_json=scores,
                    metadata_json=meta,
                )
            )
        out.sort(key=lambda x: -x.total_score)
        return out
    except Exception:
        return windows
