"""LLM-first 후보 추천 서비스.

에피소드 전체 자막을 LLM에 전달하여 쇼츠 후보 구간을 추천받는다.
기존 heuristic 파이프라인의 ScoredWindow 형식으로 변환하여 반환한다.
LLM 호출 실패 시 빈 리스트를 반환 (heuristic fallback으로 전환).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select as sa_select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Candidate, Shot, TranscriptSegment
from app.services.cache_utils import read_json_file, stable_hash, write_json_file
from app.services.candidate_generation import ScoredWindow

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 프롬프트 버전 관리
# ---------------------------------------------------------------------------

_OUTPUT_FORMAT_BLOCK = """\
## 출력 형식
JSON만 반환하세요. 다른 텍스트 없이:
{
  "candidates": [
    {
      "start_time": 120.5,
      "end_time": 175.0,
      "title": "짧고 매력적인 쇼츠 제목",
      "reason": "이 구간을 선택한 이유 (1~2문장)",
      "score": 8.5
    }
  ]
}

## 규칙
- start_time/end_time은 자막 타임스탬프 기준 초 단위
- score는 1~10 (10이 가장 좋음)
- 구간 길이는 30~75초 권장
- 서로 겹치지 않는 구간을 골라라
- score 내림차순으로 정렬해라
"""

_BASE_CRITERIA = """\
## 선정 기준
- **독립 시청 가능**: 앞뒤 맥락 없이도 이 구간만 봤을 때 이해되고 흥미로운가
- **감정 임팩트**: 웃음, 놀라움, 감동, 긴장 등 강한 감정 반응을 유발하는가
- **서사 완결성**: setup→payoff 아크가 구간 안에서 닫히는가
- **시청 유지력**: 첫 3초 안에 훅이 있고, 끝까지 볼 만한가
"""

# 장르별 추가 선정 기준
_GENRE_CRITERIA: dict[str, str] = {
    "kr_us_drama": (
        "## 장르 특화 기준 (드라마)\n"
        "- 인물 간 갈등/반전/고백 같은 서사 절정 구간 우선\n"
        "- 대사의 감정 밀도가 높은 구간 우선\n"
        "- 독백/내레이션보다 대화 아크 우선\n"
    ),
    "variety": (
        "## 장르 특화 기준 (예능)\n"
        "- 웃음 터지는 순간, 당황/놀라움 리액션 구간 우선\n"
        "- 자막 텍스트의 유머 밀도가 높은 구간 우선\n"
        "- 멤버 간 케미/대립/장난 장면 우선\n"
    ),
    "documentary": (
        "## 장르 특화 기준 (다큐)\n"
        "- 충격적 사실 공개, 반전 정보, 감동적 증언 구간 우선\n"
        "- 시청자가 '세상에' 하고 반응할 만한 정보 밀도 우선\n"
        "- 내레이션 + 영상의 조합이 강한 구간 우선\n"
    ),
}

# 프롬프트 버전별 시스템 프롬프트 생성
_PROMPT_VERSIONS: dict[str, str] = {
    "v1": (
        "당신은 한국 드라마 쇼츠 편집 전문가입니다.\n"
        "에피소드 전체 자막(타임스탬프 포함)을 읽고, 쇼츠(30~75초 세로형 숏폼)로 뽑을 만한 구간을 추천합니다.\n\n"
        "{criteria}\n{genre_criteria}\n{output_format}"
    ),
    "v2": (
        "당신은 숏폼 콘텐츠 큐레이터입니다.\n"
        "아래 드라마 에피소드 자막을 분석해 시청자가 끝까지 볼 만한 30~75초 클립 후보를 골라주세요.\n"
        "시청자 관점에서 '이거 뭐야?' 하고 눌러볼 만한 구간을 최우선으로 삼으세요.\n\n"
        "{criteria}\n{genre_criteria}\n{output_format}"
    ),
}


def _build_system_prompt(prompt_version: str, target_channel: str) -> str:
    """프롬프트 버전과 장르에 맞는 시스템 프롬프트를 조합한다."""
    template = _PROMPT_VERSIONS.get(prompt_version, _PROMPT_VERSIONS["v1"])
    genre_criteria = _GENRE_CRITERIA.get(target_channel, "")
    return template.format(
        criteria=_BASE_CRITERIA,
        genre_criteria=genre_criteria,
        output_format=_OUTPUT_FORMAT_BLOCK,
    )


# ---------------------------------------------------------------------------
# 캐싱
# ---------------------------------------------------------------------------

def _cache_key(
    transcript_text: str,
    prompt_version: str,
    target_channel: str,
    model: str,
    max_suggestions: int,
) -> str:
    """캐시 키 생성 — 자막 + 프롬프트 버전 + 장르 + 모델 조합의 해시."""
    return stable_hash({
        "transcript": transcript_text,
        "prompt_version": prompt_version,
        "target_channel": target_channel,
        "model": model,
        "max_suggestions": max_suggestions,
    })


def _cache_dir() -> Path:
    settings = get_settings()
    return settings.resolved_storage_root / "cache" / "llm_candidates"


def _read_cache(key: str) -> list[dict[str, float | str]] | None:
    path = _cache_dir() / f"{key}.json"
    data = read_json_file(path)
    if not data:
        return None
    candidates = data.get("candidates")
    if isinstance(candidates, list):
        return candidates
    return None


def _write_cache(key: str, candidates: list[dict[str, float | str]]) -> None:
    path = _cache_dir() / f"{key}.json"
    write_json_file(path, {"candidates": candidates})


@dataclass
class LlmSuggestion:
    start_time: float
    end_time: float
    title: str
    reason: str
    score: float


def _format_transcript_for_llm(segments: list[TranscriptSegment]) -> str:
    """자막 세그먼트를 LLM 입력용 텍스트로 변환한다."""
    lines: list[str] = []
    for seg in segments:
        start = f"{seg.start_time:.1f}"
        end = f"{seg.end_time:.1f}"
        text = (seg.text or "").strip().replace("\n", " ")
        if text:
            lines.append(f"[{start}–{end}] {text}")
    return "\n".join(lines)


def _parse_llm_response(content: str) -> list[LlmSuggestion]:
    """LLM JSON 응답을 파싱한다."""
    # JSON 블록 추출 (```json ... ``` 래핑 대응)
    text = content.strip()
    if text.startswith("```"):
        first_newline = text.index("\n")
        last_backtick = text.rfind("```")
        text = text[first_newline + 1:last_backtick].strip()

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    raw_candidates = parsed.get("candidates", [])
    if not isinstance(raw_candidates, list):
        return []

    suggestions: list[LlmSuggestion] = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        try:
            suggestions.append(LlmSuggestion(
                start_time=float(item.get("start_time", 0)),
                end_time=float(item.get("end_time", 0)),
                title=str(item.get("title", "")),
                reason=str(item.get("reason", "")),
                score=max(1.0, min(10.0, float(item.get("score", 5)))),
            ))
        except (ValueError, TypeError):
            continue

    return [s for s in suggestions if s.end_time > s.start_time]


def _build_few_shot_examples(db: Session | None, max_count: int = 5) -> str:
    """DB에서 selected=True인 후보의 transcript_excerpt + title_hint를 few-shot 예시로 조합한다."""
    if db is None or max_count <= 0:
        return ""

    rows = list(
        db.scalars(
            sa_select(Candidate)
            .where(Candidate.selected == True)  # noqa: E712
            .order_by(Candidate.created_at.desc())
            .limit(max_count)
        )
    )
    if not rows:
        return ""

    lines: list[str] = ["## 이전에 채택된 쇼츠 예시 (참고용)"]
    for c in rows:
        meta = c.metadata_json if isinstance(c.metadata_json, dict) else {}
        excerpt = str(meta.get("transcript_excerpt", ""))[:200]
        title = c.title_hint or ""
        lines.append(f"- [{c.start_time:.1f}–{c.end_time:.1f}] \"{title}\" — {excerpt}")
    lines.append("")
    return "\n".join(lines)


def suggest_candidates_with_llm(
    segments: list[TranscriptSegment],
    *,
    max_suggestions: int = 10,
    target_channel: str = "kr_us_drama",
    db: Session | None = None,
) -> list[LlmSuggestion]:
    """LLM에 자막을 보내 후보 구간을 추천받는다.

    Args:
        segments: 에피소드 자막 세그먼트 리스트
        max_suggestions: 최대 추천 수
        target_channel: 에피소드 장르/채널 (장르별 프롬프트 분기)
        db: DB 세션 (few-shot 예시 조회용, 없으면 few-shot 비활성)

    Returns:
        추천 구간 리스트. LLM 호출 실패 시 빈 리스트 (heuristic fallback으로 전환).
    """
    settings = get_settings()

    if not settings.openai_api_key:
        if settings.allow_mock_llm_fallback:
            logger.info("LLM candidate: API 키 없음 — heuristic fallback 사용")
            return []
        raise RuntimeError("OPENAI_API_KEY가 설정되지 않았습니다")

    transcript_text = _format_transcript_for_llm(segments)
    if not transcript_text.strip():
        logger.info("LLM candidate: 자막 없음 — heuristic fallback 사용")
        return []

    prompt_version = settings.llm_candidate_prompt_version
    model = settings.llm_candidate_model

    # --- 캐시 조회 ---
    if settings.llm_candidate_cache_enabled:
        key = _cache_key(transcript_text, prompt_version, target_channel, model, max_suggestions)
        cached = _read_cache(key)
        if cached is not None:
            suggestions = _parse_llm_response(json.dumps({"candidates": cached}))
            logger.info("LLM candidate: 캐시 히트 (%d건, key=%s…)", len(suggestions), key[:12])
            return suggestions[:max_suggestions]
    else:
        key = ""

    # --- few-shot 예시 조합 ---
    few_shot_block = _build_few_shot_examples(db, settings.llm_candidate_few_shot_count)

    # --- LLM 호출 ---
    system_prompt = _build_system_prompt(prompt_version, target_channel)
    if few_shot_block:
        system_prompt = system_prompt + "\n" + few_shot_block

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)

    try:
        response = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"아래 에피소드 자막에서 쇼츠 후보 구간을 최대 {max_suggestions}개 추천해주세요.\n\n"
                        f"{transcript_text}"
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or ""
        suggestions = _parse_llm_response(content)
        logger.info(
            "LLM candidate: %d개 구간 추천 수신 (model=%s, prompt=%s, channel=%s)",
            len(suggestions), model, prompt_version, target_channel,
        )

        # --- 캐시 저장 ---
        if settings.llm_candidate_cache_enabled and key and suggestions:
            cache_data: list[dict[str, float | str]] = [
                {
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "title": s.title,
                    "reason": s.reason,
                    "score": s.score,
                }
                for s in suggestions
            ]
            _write_cache(key, cache_data)

        return suggestions[:max_suggestions]

    except Exception:
        logger.warning("LLM candidate 호출 실패 — heuristic fallback 사용", exc_info=True)
        if settings.allow_mock_llm_fallback:
            return []
        raise


def _snap_to_shot_boundaries(
    start: float,
    end: float,
    shots: list[Shot],
    max_shift: float = 5.0,
) -> tuple[float, float]:
    """LLM 추천 구간을 가장 가까운 샷 경계로 스냅한다.

    각 끝점에서 max_shift초 이내의 가장 가까운 샷 경계를 찾는다.
    샷이 없거나 범위 내에 경계가 없으면 원본 값을 유지한다.
    """
    if not shots:
        return start, end

    shot_starts = [float(s.start_time) for s in shots]
    shot_ends = [float(s.end_time) for s in shots]
    all_boundaries = sorted(set(shot_starts + shot_ends))

    snapped_start = start
    best_start_dist = max_shift
    for b in all_boundaries:
        dist = abs(b - start)
        if dist < best_start_dist:
            best_start_dist = dist
            snapped_start = b

    snapped_end = end
    best_end_dist = max_shift
    for b in all_boundaries:
        dist = abs(b - end)
        if dist < best_end_dist:
            best_end_dist = dist
            snapped_end = b

    if snapped_end <= snapped_start:
        return start, end

    return round(snapped_start, 3), round(snapped_end, 3)


def _snap_end_to_sentence_boundary(
    start: float,
    end: float,
    segments: list[TranscriptSegment],
    max_pull: float = 8.0,
    min_duration: float = 25.0,
) -> float:
    """끝점을 구간 내 마지막 완결 자막 문장의 end_time으로 당긴다.

    대화 중간에서 잘리는 걸 방지. 구간 끝에서 max_pull초 이내의
    가장 마지막 자막 종료 시점으로 스냅한다.
    구간이 min_duration 미만이 되면 원본 유지.
    """
    # 구간 내 자막 중 end_time이 구간 안에 있는 것들
    candidates: list[float] = []
    for seg in segments:
        seg_end = float(seg.end_time)
        # 자막이 구간 내에서 끝나고, 끝점보다 앞에 있으며, max_pull 이내
        if seg_end >= start and seg_end <= end and (end - seg_end) <= max_pull:
            candidates.append(seg_end)

    if not candidates:
        return end

    best_end = max(candidates)
    if best_end - start < min_duration:
        return end

    return round(best_end, 3)


def _detect_foreign_scene_gaps(
    start: float,
    end: float,
    segments: list[TranscriptSegment],
    shots: list[Shot],
    gap_threshold: float = 8.0,
) -> list[dict[str, float | int | str]]:
    """구간 내 자막 공백이 gap_threshold 이상인 곳을 감지해 clip_spans를 분리한다.

    "A장면→B장면(무관)→A장면" 구조에서 B를 빼고 A만 이어붙이는 composite 구조 생성.
    공백이 없으면 단일 span 반환.
    """
    # 구간 내 자막을 시간순 수집
    in_range: list[tuple[float, float]] = []
    for seg in segments:
        s = max(float(seg.start_time), start)
        e = min(float(seg.end_time), end)
        if e > s and (seg.text or "").strip():
            in_range.append((s, e))

    if not in_range:
        return [{"start_time": round(start, 3), "end_time": round(end, 3), "order": 0, "role": "main"}]

    in_range.sort()

    # 자막 구간 병합
    merged: list[tuple[float, float]] = []
    cur_s, cur_e = in_range[0]
    for s, e in in_range[1:]:
        if s <= cur_e + 1.0:  # 1초 이내 간격은 연속으로 간주
            cur_e = max(cur_e, e)
        else:
            merged.append((cur_s, cur_e))
            cur_s, cur_e = s, e
    merged.append((cur_s, cur_e))

    # 공백 감지: 병합된 자막 블록 사이 간격이 threshold 이상이면 분리
    spans: list[dict[str, float | int | str]] = []
    for idx, (block_start, block_end) in enumerate(merged):
        if idx > 0:
            prev_end = merged[idx - 1][1]
            gap = block_start - prev_end
            if gap < gap_threshold:
                # 공백이 짧으면 이전 span에 합침
                if spans:
                    spans[-1]["end_time"] = round(block_end, 3)
                    continue

        # 샷 경계에 맞춰 span 시작/끝 미세 조정
        span_start = round(block_start, 3)
        span_end = round(block_end, 3)

        # 최소 5초 이상인 span만 유지
        if span_end - span_start >= 5.0:
            role = "main" if idx == 0 else "core_payoff" if idx == len(merged) - 1 else "core_escalation"
            spans.append({
                "start_time": span_start,
                "end_time": span_end,
                "order": len(spans),
                "role": role,
            })

    if not spans:
        return [{"start_time": round(start, 3), "end_time": round(end, 3), "order": 0, "role": "main"}]

    return spans


# LLM 점수(1~10) → heuristic 스케일(1~10) 정규화 계수
# heuristic 후보의 일반적인 점수 범위는 4~8. LLM은 6~9로 높게 주는 경향.
# 이 계수를 곱해 heuristic 스케일에 맞춘다.
_LLM_SCORE_SCALE = 0.85


def llm_suggestions_to_scored_windows(
    suggestions: list[LlmSuggestion],
    segments: list[TranscriptSegment],
    shots: list[Shot] | None = None,
    episode_avg_cut_rate: float = 0.0,
) -> list[ScoredWindow]:
    """LLM 추천 구간을 ScoredWindow 리스트로 변환한다.

    - 샷 경계 스냅 (shots 제공 시)
    - 시각/오디오 보정 점수 계산
    - LLM 점수 정규화
    """
    from app.services.candidate_language_signals import extract_tokens
    from app.services.candidate_visual_signals import compute_visual_impact

    shot_list = shots or []

    windows: list[ScoredWindow] = []
    for sug in suggestions:
        # 1) 샷 경계 스냅
        snapped_start, snapped_end = _snap_to_shot_boundaries(
            sug.start_time, sug.end_time, shot_list,
        )
        duration = snapped_end - snapped_start
        if duration < 10.0:
            snapped_start, snapped_end = sug.start_time, sug.end_time
            duration = snapped_end - snapped_start

        # 1b) 끝점을 자막 문장 경계에 스냅
        snapped_end = _snap_end_to_sentence_boundary(snapped_start, snapped_end, segments)
        duration = snapped_end - snapped_start

        # 1c) 중간 이질 씬 감지 → clip_spans 분리
        clip_spans = _detect_foreign_scene_gaps(snapped_start, snapped_end, segments, shot_list)
        is_composite = len(clip_spans) > 1
        arc_form = "composite" if is_composite else "contiguous"

        # 2) 구간 내 자막 텍스트 수집
        excerpt_parts: list[str] = []
        speech_sec = 0.0
        for seg in segments:
            if seg.end_time <= snapped_start or seg.start_time >= snapped_end:
                continue
            text = (seg.text or "").strip()
            if text:
                excerpt_parts.append(text)
                overlap = min(float(seg.end_time), snapped_end) - max(float(seg.start_time), snapped_start)
                speech_sec += max(0.0, overlap)
        excerpt = " ".join(excerpt_parts)[:320]
        tokens = extract_tokens(excerpt)
        speech_coverage = min(1.0, speech_sec / max(duration, 1.0))

        # 3) 시각/오디오 보정 점수
        window_shots = [
            s for s in shot_list
            if float(s.start_time) < snapped_end and float(s.end_time) > snapped_start
        ]
        visual_impact = compute_visual_impact(
            window_shots, duration, episode_avg_cut_rate, speech_coverage,
        ) if window_shots else 0.0

        cuts_inside = sum(
            1 for s in shot_list
            if float(s.start_time) > snapped_start + 0.05 and float(s.start_time) < snapped_end - 0.05
        )

        # 4) LLM 점수 정규화
        raw_llm_score = sug.score
        normalized_score = round(max(1.0, raw_llm_score * _LLM_SCORE_SCALE), 2)

        # 시각 보정: visual_impact가 높으면 소폭 가산
        visual_bonus = round(min(0.5, visual_impact * 0.5), 2)
        total_score = round(min(10.0, normalized_score + visual_bonus), 2)

        windows.append(ScoredWindow(
            start_time=round(snapped_start, 3),
            end_time=round(snapped_end, 3),
            total_score=total_score,
            scores_json={
                "total_score": total_score,
                "llm_score": round(raw_llm_score, 2),
                "llm_score_normalized": normalized_score,
                "visual_impact": round(visual_impact, 3),
                "visual_bonus": visual_bonus,
                "speech_coverage": round(speech_coverage, 3),
                "cuts_inside": float(cuts_inside),
            },
            title_hint=sug.title[:255] if sug.title else f"구간 {snapped_start:.1f}–{snapped_end:.1f}s",
            metadata_json={
                "generated_by": "llm_candidate_v1",
                "candidate_track": "llm",
                "arc_form": arc_form,
                "composite": is_composite,
                "window_reason": "llm_recommendation",
                "llm_reason": sug.reason,
                "llm_score": round(raw_llm_score, 2),
                "llm_score_normalized": normalized_score,
                "shot_snapped": (snapped_start != sug.start_time or snapped_end != sug.end_time),
                "sentence_snapped": (snapped_end != sug.end_time),
                "original_start": round(sug.start_time, 3),
                "original_end": round(sug.end_time, 3),
                "transcript_excerpt": excerpt,
                "dedupe_tokens": tokens[:16],
                "dominant_entities": [],
                "ranking_focus": "llm_recommended",
                "visual_impact": round(visual_impact, 4),
                "speech_coverage": round(speech_coverage, 4),
                "clip_spans": clip_spans,
                "source_events": [],
            },
        ))

    return windows


# ---------------------------------------------------------------------------
# Pass 2: LLM 검증
# ---------------------------------------------------------------------------

_VERIFY_SYSTEM_PROMPT = """\
당신은 한국 드라마 쇼츠 편집 검증 전문가입니다.
후보 구간의 자막 발췌를 읽고, 쇼츠로 적합한지 검증합니다.

각 후보에 대해 JSON으로만 응답하세요:
{
  "results": [
    {
      "index": 0,
      "keep": true,
      "adjusted_start": 120.5,
      "adjusted_end": 170.0,
      "final_score": 8.0,
      "reason": "판정 이유 (1~2문장)"
    }
  ]
}

## 판정 기준
- **keep=true**: 맥락 없이도 재밌고, 서사 아크가 완결되며, 시청 유지력이 있음
- **keep=false**: 맥락 없이 이해 불가, payoff 없이 끊김, 지루함
- **adjusted_start/end**: 시작/끝을 조정하면 더 나을 때만 변경. 그대로면 원본 값 유지.
- **final_score**: 1~10 (검증 후 재산정)
"""


@dataclass
class VerifyResult:
    index: int
    keep: bool
    adjusted_start: float
    adjusted_end: float
    final_score: float
    reason: str


def _parse_verify_response(content: str) -> list[VerifyResult]:
    """Pass 2 검증 응답을 파싱한다."""
    text = content.strip()
    if text.startswith("```"):
        first_nl = text.index("\n")
        last_bt = text.rfind("```")
        text = text[first_nl + 1:last_bt].strip()

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []

    raw_results = parsed.get("results", [])
    if not isinstance(raw_results, list):
        return []

    results: list[VerifyResult] = []
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        try:
            results.append(VerifyResult(
                index=int(item.get("index", -1)),
                keep=bool(item.get("keep", True)),
                adjusted_start=float(item.get("adjusted_start", 0)),
                adjusted_end=float(item.get("adjusted_end", 0)),
                final_score=max(1.0, min(10.0, float(item.get("final_score", 5)))),
                reason=str(item.get("reason", "")),
            ))
        except (ValueError, TypeError):
            continue
    return results


def verify_candidates_with_llm(
    suggestions: list[LlmSuggestion],
    segments: list[TranscriptSegment],
) -> list[LlmSuggestion]:
    """Pass 2: LLM으로 후보를 검증하여 부적격 탈락 + 트림 조정.

    Returns:
        검증 통과한 LlmSuggestion 리스트 (score/start/end 조정 반영).
        LLM 호출 실패 시 원본 그대로 반환.
    """
    settings = get_settings()

    if not suggestions:
        return []
    if not settings.openai_api_key:
        return suggestions

    # 각 후보의 자막 발췌 구성
    candidate_blocks: list[str] = []
    for idx, sug in enumerate(suggestions):
        parts: list[str] = []
        for seg in segments:
            if seg.end_time <= sug.start_time or seg.start_time >= sug.end_time:
                continue
            text = (seg.text or "").strip()
            if text:
                parts.append(f"[{seg.start_time:.1f}–{seg.end_time:.1f}] {text}")
        excerpt = "\n".join(parts)[:500]
        candidate_blocks.append(
            f"### 후보 {idx}\n"
            f"구간: {sug.start_time:.1f}–{sug.end_time:.1f}초\n"
            f"제목: {sug.title}\n"
            f"사유: {sug.reason}\n"
            f"점수: {sug.score}\n"
            f"자막:\n{excerpt}"
        )

    user_content = (
        f"아래 {len(suggestions)}개 쇼츠 후보를 검증해주세요.\n\n"
        + "\n\n".join(candidate_blocks)
    )

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)

    try:
        response = client.chat.completions.create(
            model=settings.llm_candidate_verify_model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _VERIFY_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
        )
        content = response.choices[0].message.content or ""
        results = _parse_verify_response(content)
        logger.info("LLM verify: %d건 응답 수신", len(results))
    except Exception:
        logger.warning("LLM verify 호출 실패 — 원본 유지", exc_info=True)
        return suggestions

    # 결과 적용
    result_map: dict[int, VerifyResult] = {r.index: r for r in results}
    verified: list[LlmSuggestion] = []
    for idx, sug in enumerate(suggestions):
        vr = result_map.get(idx)
        if vr is None:
            # 검증 응답에 없으면 유지
            verified.append(sug)
            continue
        if not vr.keep:
            logger.info("LLM verify: 후보 %d 탈락 — %s", idx, vr.reason)
            continue
        # 트림 조정 + 점수 재산정
        verified.append(LlmSuggestion(
            start_time=vr.adjusted_start if vr.adjusted_start > 0 else sug.start_time,
            end_time=vr.adjusted_end if vr.adjusted_end > 0 else sug.end_time,
            title=sug.title,
            reason=f"{sug.reason} | 검증: {vr.reason}",
            score=vr.final_score,
        ))

    logger.info("LLM verify: %d → %d건 (탈락 %d건)", len(suggestions), len(verified), len(suggestions) - len(verified))
    return verified
