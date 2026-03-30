from __future__ import annotations

import base64
import json
from dataclasses import replace
from pathlib import Path
from typing import Any, Sequence

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Episode, Shot, TranscriptSegment
from app.services.cache_utils import file_signature, read_json_file, stable_hash, write_json_file
from app.services.candidate_generation import ScoredWindow
from app.services.storage_service import episode_root


def _strip_json_fence(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return text.strip()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _transcript_excerpt_for_window(
    segments: Sequence[TranscriptSegment],
    start: float,
    end: float,
    *,
    max_chars: int = 900,
) -> str:
    parts: list[str] = []
    total = 0
    for seg in segments:
        if float(seg.end_time) <= start or float(seg.start_time) >= end:
            continue
        line = (seg.text or "").strip().replace("\n", " ")
        if not line:
            continue
        parts.append(line)
        total += len(line) + 1
        if total >= max_chars:
            break
    return " ".join(parts)[:max_chars]


def _candidate_shots(shots: Sequence[Shot], start: float, end: float) -> list[Shot]:
    return [
        shot for shot in shots if float(shot.start_time) <= end and float(shot.end_time) >= start
    ]


def _shot_frame_paths(episode_id: str, shot_index: int) -> list[Path]:
    shot_dir = episode_root(episode_id) / "shots" / f"{int(shot_index):04d}"
    if not shot_dir.is_dir():
        return []
    return sorted(
        [
            path
            for path in shot_dir.glob("frame_*.jpg")
            if path.is_file() and path.stat().st_size > 80
        ]
    )


def _sample_frame_paths(paths: Sequence[Path], limit: int) -> list[Path]:
    if limit <= 0:
        return []
    if len(paths) <= limit:
        return list(paths)
    if limit == 1:
        return [paths[len(paths) // 2]]
    sampled: list[Path] = []
    last_index = len(paths) - 1
    for slot in range(limit):
        index = round(slot * last_index / (limit - 1))
        sampled.append(paths[index])
    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in sampled:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    return deduped


def _candidate_frame_paths(episode_id: str, shots: Sequence[Shot], limit: int) -> list[Path]:
    paths: list[Path] = []
    for shot in shots:
        paths.extend(_shot_frame_paths(episode_id, int(shot.shot_index)))
    return _sample_frame_paths(paths, limit)


def _vision_cache_path(episode_id: str) -> Path:
    return episode_root(episode_id) / "cache" / "vision_rerank.json"


def _vision_cache_key(
    *,
    episode: Episode,
    window: ScoredWindow,
    transcript_excerpt: str,
    frame_paths: Sequence[Path],
) -> str:
    settings = get_settings()
    return stable_hash(
        {
            "episode_id": episode.id,
            "model": settings.vision_model,
            "prompt_version": settings.vision_prompt_version,
            "window": {
                "start_time": round(window.start_time, 3),
                "end_time": round(window.end_time, 3),
                "title_hint": window.title_hint[:180],
                "heuristic_total_score": window.total_score,
            },
            "transcript_excerpt": transcript_excerpt,
            "frames": [file_signature(path) for path in frame_paths],
        }
    )


def _image_part(path: Path) -> dict[str, Any]:
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:image/jpeg;base64,{data}",
            "detail": "low",
        },
    }


def _vision_request_payload(
    episode: Episode,
    window: ScoredWindow,
    transcript_excerpt: str,
    frame_paths: Sequence[Path],
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "show_title": episode.show_title,
                    "episode_title": episode.episode_title,
                    "candidate_window": {
                        "start_sec": window.start_time,
                        "end_sec": window.end_time,
                        "duration_sec": round(window.end_time - window.start_time, 2),
                        "heuristic_total_score": window.total_score,
                        "title_hint": window.title_hint[:180],
                    },
                    "transcript_excerpt": transcript_excerpt,
                    "instruction": (
                        "Frames are ordered chronologically. "
                        "Judge whether the clip has a clear hook, emotional turn, self-contained context, "
                        "and strong thumbnail potential for Korean shorts commentary."
                    ),
                },
                ensure_ascii=False,
            ),
        }
    ]
    payload.extend(_image_part(path) for path in frame_paths)
    return payload


def _call_vision_model(
    client: OpenAI,
    episode: Episode,
    window: ScoredWindow,
    transcript_excerpt: str,
    frame_paths: Sequence[Path],
) -> dict[str, Any] | None:
    settings = get_settings()
    response = client.chat.completions.create(
        model=settings.vision_model,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": (
                    "당신은 한국 드라마 쇼츠 채널의 편집 전문가입니다.\n"
                    "제공된 프레임(시간 순서)과 자막 발췌문을 함께 보고 후보 클립을 평가하세요.\n\n"
                    "반환 형식 — 아래 키만 포함된 JSON (다른 텍스트 없이):\n"
                    "  score_delta (-1.5..1.5): 휴리스틱 점수 조정값\n"
                    "  visual_hook_score (0..10): 첫 프레임/장면의 시각적 훅 강도\n"
                    "  self_contained_score (0..10): 앞뒤 맥락 없이 독립 이해 가능 정도\n"
                    "  emotion_shift_score (0..10): 감정 전환·반전의 강도\n"
                    "  thumbnail_strength_score (0..10): 썸네일로 클릭을 유도할 강도\n"
                    "  vision_reason (한국어, 최대 140자): 평가 근거\n"
                    "  title_hint (최대 90자 또는 null): 추천 제목\n"
                    "  note (최대 220자 또는 null): 추가 메모\n\n"
                    "## 강하게 보상 (+score_delta)\n"
                    "- 웃긴/역설적/황당한 상황 (코미디·반전)\n"
                    "- 감동적·공감 장면 (울컥, 화해, 고백)\n"
                    "- 강한 감정 폭발 또는 표정 변화 (반응 클립)\n"
                    "- 자막 없이도 의미 전달되는 시각적 스토리\n"
                    "- 30~75초 내 기승전결이 완결되는 구조\n\n"
                    "## 패널티 (-score_delta)\n"
                    "- 앞 장면 없이 전혀 이해 불가한 맥락 의존 클립\n"
                    "- 감정 결말 없이 중간에서 끊기는 클립\n"
                    "- 어두운 화면, 빈 자막, 시각적 임팩트 없음\n"
                    "- 단순 정보 전달만 있고 감정·갈등 없음\n\n"
                    "프레임이 약하거나 자막이 비어 있으면 score_delta를 0 또는 음수로 유지하세요."
                ),
            },
            {
                "role": "user",
                "content": _vision_request_payload(
                    episode=episode,
                    window=window,
                    transcript_excerpt=transcript_excerpt,
                    frame_paths=frame_paths,
                ),
            },
        ],
        temperature=0.25,
        max_tokens=500,
    )
    raw = response.choices[0].message.content or "{}"
    data = json.loads(_strip_json_fence(raw))
    return data if isinstance(data, dict) else None


def _apply_vision_scores(
    window: ScoredWindow,
    payload: dict[str, Any],
    *,
    episode_id: str,
    frame_paths: Sequence[Path],
) -> ScoredWindow:
    settings = get_settings()
    try:
        delta_raw = float(payload.get("score_delta", 0.0) or 0.0)
    except (TypeError, ValueError):
        delta_raw = 0.0
    delta = _clamp(delta_raw, -1.5, 1.5)
    total_score = round(_clamp(window.total_score + delta, 1.0, 10.0), 2)
    try:
        visual_hook_raw = float(payload.get("visual_hook_score", total_score) or total_score)
    except (TypeError, ValueError):
        visual_hook_raw = total_score
    try:
        self_contained_raw = float(payload.get("self_contained_score", total_score) or total_score)
    except (TypeError, ValueError):
        self_contained_raw = total_score
    try:
        emotion_shift_raw = float(payload.get("emotion_shift_score", total_score) or total_score)
    except (TypeError, ValueError):
        emotion_shift_raw = total_score
    try:
        thumbnail_strength_raw = float(
            payload.get("thumbnail_strength_score", total_score) or total_score
        )
    except (TypeError, ValueError):
        thumbnail_strength_raw = total_score
    visual_hook_score = round(_clamp(visual_hook_raw, 0.0, 10.0), 2)
    self_contained_score = round(_clamp(self_contained_raw, 0.0, 10.0), 2)
    emotion_shift_score = round(_clamp(emotion_shift_raw, 0.0, 10.0), 2)
    thumbnail_strength_score = round(_clamp(thumbnail_strength_raw, 0.0, 10.0), 2)
    title_hint = window.title_hint
    if isinstance(payload.get("title_hint"), str) and payload["title_hint"].strip():
        title_hint = payload["title_hint"].strip()[:255]

    scores = dict(window.scores_json)
    scores["total_score"] = total_score
    scores["visual_hook_score"] = visual_hook_score
    scores["self_contained_score"] = self_contained_score
    scores["emotion_shift_score"] = emotion_shift_score
    scores["thumbnail_strength_score"] = thumbnail_strength_score
    scores["vision_score_delta"] = round(delta, 2)

    metadata = dict(window.metadata_json)
    metadata["generated_by"] = "heuristic_v1 + vision_v1"
    metadata["vision_rerank_status"] = "applied"
    metadata["vision_score_delta"] = round(delta, 2)
    metadata["vision_reason"] = str(payload.get("vision_reason") or "").strip()[:300]
    metadata["vision_model"] = settings.vision_model
    metadata["vision_prompt_version"] = settings.vision_prompt_version
    metadata["vision_frame_count"] = len(frame_paths)
    metadata["vision_frames"] = [
        str(path.relative_to(episode_root(episode_id))) for path in frame_paths
    ]
    note = payload.get("note")
    if isinstance(note, str) and note.strip():
        metadata["llm_note"] = note.strip()[:300]

    return replace(
        window,
        total_score=total_score,
        title_hint=title_hint,
        scores_json=scores,
        metadata_json=metadata,
    )


def refine_candidates_with_vision(
    db: Session,
    episode: Episode,
    windows: list[ScoredWindow],
    *,
    ignore_cache: bool = False,
) -> tuple[list[ScoredWindow], dict[str, Any]]:
    settings = get_settings()
    summary: dict[str, Any] = {
        "enabled": settings.vision_rerank_enabled,
        "status": "skipped",
        "model": settings.vision_model,
        "prompt_version": settings.vision_prompt_version,
        "candidate_limit": max(0, int(settings.vision_max_candidates_per_episode)),
        "frame_limit": max(0, int(settings.vision_max_frames_per_candidate)),
        "applied_candidates": 0,
        "attempted_candidates": 0,
        "cache_hits": 0,
        "fallback_reasons": [],
    }
    if not windows:
        summary["reason"] = "no_candidates"
        return windows, summary
    if not settings.vision_rerank_enabled:
        summary["reason"] = "feature_off"
        return windows, summary
    if not settings.openai_api_key:
        summary["reason"] = "missing_openai_api_key"
        return windows, summary
    if summary["candidate_limit"] <= 0:
        summary["reason"] = "candidate_limit_zero"
        return windows, summary
    if summary["frame_limit"] <= 0:
        summary["reason"] = "frame_limit_zero"
        return windows, summary

    shots = list(
        db.scalars(
            select(Shot).where(Shot.episode_id == episode.id).order_by(Shot.shot_index.asc())
        )
    )
    segments = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.episode_id == episode.id)
            .order_by(TranscriptSegment.start_time.asc())
        )
    )
    if not shots:
        summary["reason"] = "no_shots"
        return windows, summary

    cache_path = _vision_cache_path(episode.id)
    cache_data = read_json_file(cache_path)
    cache_entries = dict(cache_data.get("entries") or {})
    client = OpenAI(api_key=settings.openai_api_key)
    refined = list(windows)
    for index, window in enumerate(refined[: summary["candidate_limit"]]):
        candidate_shots = _candidate_shots(shots, window.start_time, window.end_time)
        frame_paths = _candidate_frame_paths(episode.id, candidate_shots, summary["frame_limit"])
        if not frame_paths:
            summary["fallback_reasons"].append(
                {"candidate_index": index + 1, "reason": "missing_keyframes"}
            )
            continue
        transcript_excerpt = _transcript_excerpt_for_window(
            segments, window.start_time, window.end_time
        )
        cache_key = _vision_cache_key(
            episode=episode,
            window=window,
            transcript_excerpt=transcript_excerpt,
            frame_paths=frame_paths,
        )
        cached_payload = cache_entries.get(cache_key)
        if not ignore_cache and isinstance(cached_payload, dict):
            try:
                refined[index] = _apply_vision_scores(
                    window,
                    cached_payload,
                    episode_id=episode.id,
                    frame_paths=frame_paths,
                )
                summary["applied_candidates"] += 1
                summary["cache_hits"] += 1
                continue
            except Exception:
                cache_entries.pop(cache_key, None)
        summary["attempted_candidates"] += 1
        try:
            payload = _call_vision_model(
                client=client,
                episode=episode,
                window=window,
                transcript_excerpt=transcript_excerpt,
                frame_paths=frame_paths,
            )
        except Exception as exc:
            summary["fallback_reasons"].append(
                {"candidate_index": index + 1, "reason": f"vision_call_failed:{str(exc)[:120]}"}
            )
            continue
        if not payload:
            summary["fallback_reasons"].append(
                {"candidate_index": index + 1, "reason": "empty_model_response"}
            )
            continue
        try:
            refined[index] = _apply_vision_scores(
                window,
                payload,
                episode_id=episode.id,
                frame_paths=frame_paths,
            )
            summary["applied_candidates"] += 1
            cache_entries[cache_key] = payload
        except Exception as exc:
            summary["fallback_reasons"].append(
                {"candidate_index": index + 1, "reason": f"parse_failed:{str(exc)[:120]}"}
            )

    refined.sort(key=lambda item: -item.total_score)
    write_json_file(
        cache_path,
        {
            "model": settings.vision_model,
            "prompt_version": settings.vision_prompt_version,
            "entries": cache_entries,
        },
    )
    summary["status"] = "completed" if summary["applied_candidates"] > 0 else "fallback"
    if summary["status"] == "fallback" and not summary["fallback_reasons"]:
        summary["reason"] = "no_candidate_applied"
    return refined, summary
