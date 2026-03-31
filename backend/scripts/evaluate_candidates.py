#!/usr/bin/env python3
"""오프라인 후보 품질 평가 스크립트.

golden_candidates.json(사람이 선별한 정답 후보)과 파이프라인 출력을
비교해 Recall@K, 점수 분포, 타임라인 커버리지, 실패 유형 분포를 계산한다.

사용법:
    # 평가 실행
    python scripts/evaluate_candidates.py \\
        --golden golden_candidates.json \\
        --db sqlite:///data/app.db \\
        [--episode-ids ep1 ep2] \\
        [--top-k 5 10 14] \\
        [--iou-threshold 0.3]

    # golden JSON 템플릿 생성 (DB에서 기존 후보를 기반으로)
    python scripts/evaluate_candidates.py \\
        --create-golden-template golden_draft.json \\
        --episode-ids ep1 ep2 \\
        [--db sqlite:///data/app.db]

    # DB에서 후보 목록을 golden seed로 내보내기
    python scripts/evaluate_candidates.py \\
        --export-candidates candidates_seed.json \\
        --episode-ids ep1 ep2

golden_candidates.json 형식 (v2):
    {
      "version": 2,
      "description": "Golden set 설명",
      "episodes": {
        "<episode_id>": {
          "title": "에피소드 제목 (선택)",
          "candidates": [
            {
              "start_time": 100.0,
              "end_time": 160.0,
              "label": "좋은 후보 1",
              "quality": "good",
              "failure_types": [],
              "notes": ""
            }
          ]
        }
      }
    }

v1 형식(플랫 dict)도 하위 호환으로 지원.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from statistics import mean, stdev
from typing import Literal, NamedTuple

# 프로젝트 루트를 sys.path에 추가
_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", f"sqlite:///{_BACKEND_DIR / 'data' / 'app.db'}")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("OPENAI_API_KEY", "")

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.models import Candidate, CandidateFeedback, Episode  # noqa: E402

# §6.1 실패 유형 분류 체계
FAILURE_TYPES: list[str] = [
    "context_missing",         # 맥락 결여 — 독립 시청 불가
    "no_payoff",               # payoff 없이 끊김
    "duplicate_similar",       # 유사 후보 중복 상위 노출
    "too_long",                # 지나치게 긴 후보
    "weak_narrative",          # 시각적으로는 강하지만 서사 약함
    "weak_structure",          # 쇼츠 구조 약함 (hookability 낮음)
    "composite_overconnect",   # 복합 후보 과연결
]

GoldenQuality = Literal["good", "acceptable", "bad"]


class GoldenEntry(NamedTuple):
    start_time: float
    end_time: float
    label: str
    quality: GoldenQuality
    failure_types: list[str]
    notes: str


def _load_golden(path: Path) -> dict[str, list[GoldenEntry]]:
    with path.open(encoding="utf-8") as f:
        raw = json.load(f)

    # v2 형식 감지
    if isinstance(raw, dict) and "episodes" in raw:
        episodes_dict: dict[str, dict] = raw["episodes"]
        result: dict[str, list[GoldenEntry]] = {}
        for episode_id, ep_data in episodes_dict.items():
            candidates_list = ep_data.get("candidates", [])
            result[episode_id] = [
                GoldenEntry(
                    start_time=float(e.get("start_time", 0.0)),
                    end_time=float(e.get("end_time", 0.0)),
                    label=str(e.get("label", "")),
                    quality=e.get("quality", "good"),
                    failure_types=list(e.get("failure_types") or []),
                    notes=str(e.get("notes", "")),
                )
                for e in candidates_list
            ]
        return result

    # v1 형식 하위 호환
    result_v1: dict[str, list[GoldenEntry]] = {}
    for episode_id, entries in raw.items():
        result_v1[episode_id] = [
            GoldenEntry(
                start_time=float(e.get("start_time", 0.0)),
                end_time=float(e.get("end_time", 0.0)),
                label=str(e.get("label", "")),
                quality=e.get("quality", "good"),
                failure_types=list(e.get("failure_types") or []),
                notes=str(e.get("notes", "")),
            )
            for e in entries
        ]
    return result_v1


def _temporal_iou(
    a_start: float,
    a_end: float,
    b_start: float,
    b_end: float,
) -> float:
    overlap = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    union = max(0.0, max(a_end, b_end) - min(a_start, b_start))
    return overlap / union if union > 0 else 0.0


def _recall_at_k(
    candidates: list[Candidate],
    golden: list[GoldenEntry],
    *,
    k: int,
    iou_threshold: float = 0.3,
) -> tuple[float, list[dict[str, str | float | bool]]]:
    """Top-K 후보 중 golden과 IOU ≥ threshold로 매칭되는 비율.

    Returns (recall, match_details) — match_details는 golden 항목별 매칭 결과.
    """
    if not golden:
        return 0.0, []
    top_k = candidates[:k]
    matched = 0
    match_details: list[dict[str, str | float | bool]] = []
    for entry in golden:
        best_iou = 0.0
        best_cand_idx = -1
        for idx, cand in enumerate(top_k):
            iou = _temporal_iou(
                float(cand.start_time), float(cand.end_time),
                entry.start_time, entry.end_time,
            )
            if iou > best_iou:
                best_iou = iou
                best_cand_idx = idx
        is_match = best_iou >= iou_threshold
        if is_match:
            matched += 1
        match_details.append({
            "golden_label": entry.label,
            "golden_start": entry.start_time,
            "golden_end": entry.end_time,
            "quality": entry.quality,
            "matched": is_match,
            "best_iou": round(best_iou, 3),
            "best_candidate_rank": best_cand_idx + 1 if best_cand_idx >= 0 else -1,
        })
    return matched / len(golden), match_details


def _timeline_coverage(candidates: list[Candidate], episode_duration: float) -> float:
    """후보들이 에피소드 전체 타임라인 중 커버하는 비율 (중복 제거)."""
    if not candidates or episode_duration <= 0:
        return 0.0
    intervals: list[tuple[float, float]] = sorted(
        (float(c.start_time), float(c.end_time)) for c in candidates
    )
    merged: list[tuple[float, float]] = []
    for start, end in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    covered = sum(end - start for start, end in merged)
    return min(1.0, covered / episode_duration)


def _failure_type_distribution(golden: list[GoldenEntry]) -> dict[str, int]:
    """golden set에서 실패 유형별 빈도 집계."""
    counts: dict[str, int] = {ft: 0 for ft in FAILURE_TYPES}
    for entry in golden:
        for ft in entry.failure_types:
            if ft in counts:
                counts[ft] += 1
    return {k: v for k, v in counts.items() if v > 0}


def _quality_distribution(golden: list[GoldenEntry]) -> dict[str, int]:
    """golden set에서 quality 등급별 수."""
    dist: dict[str, int] = {"good": 0, "acceptable": 0, "bad": 0}
    for entry in golden:
        if entry.quality in dist:
            dist[entry.quality] += 1
    return dist


def evaluate_pipeline(
    db: Session,
    golden: dict[str, list[GoldenEntry]],
    episode_ids: list[str] | None = None,
    top_ks: tuple[int, ...] = (5, 10, 14),
    iou_threshold: float = 0.3,
) -> dict[str, dict]:
    target_ids = episode_ids or list(golden.keys())
    results: dict[str, dict] = {}

    for episode_id in target_ids:
        candidates = list(
            db.scalars(
                select(Candidate)
                .where(Candidate.episode_id == episode_id)
                .order_by(Candidate.total_score.desc())
            )
        )
        if not candidates:
            results[episode_id] = {"error": "후보 없음"}
            continue

        golden_entries = golden.get(episode_id, [])
        good_entries = [e for e in golden_entries if e.quality == "good"]
        scores = [float(c.total_score) for c in candidates]

        recall_at_k: dict[str, float] = {}
        match_details_at_k: dict[str, list[dict[str, str | float | bool]]] = {}
        for k in top_ks:
            recall, details = _recall_at_k(
                candidates, good_entries, k=k, iou_threshold=iou_threshold,
            )
            recall_at_k[f"recall@{k}"] = round(recall, 3)
            match_details_at_k[f"recall@{k}"] = details

        score_stats: dict[str, float] = {
            "mean": round(mean(scores), 3),
            "std": round(stdev(scores), 3) if len(scores) >= 2 else 0.0,
            "top3_avg": round(mean(scores[:3]), 3),
            "max": round(max(scores), 3),
            "min": round(min(scores), 3),
        }

        # 에피소드 duration: 마지막 후보 end_time으로 근사
        ep_duration = max(float(c.end_time) for c in candidates)
        coverage = round(_timeline_coverage(candidates, ep_duration), 3)

        n_composite = sum(
            1 for c in candidates
            if isinstance(c.metadata_json, dict) and c.metadata_json.get("composite")
        )

        audio_track_candidate_count = sum(
            1 for c in candidates
            if isinstance(c.metadata_json, dict)
            and c.metadata_json.get("candidate_track") == "audio"
        )

        embedding_used_candidate_count = sum(
            1 for c in candidates
            if isinstance(c.metadata_json, dict) and c.metadata_json.get("embedding_used")
        )

        # 트랙별 분포
        track_distribution: dict[str, int] = {}
        for c in candidates:
            meta = c.metadata_json if isinstance(c.metadata_json, dict) else {}
            track = str(meta.get("candidate_track", "dialogue"))
            track_distribution[track] = track_distribution.get(track, 0) + 1

        results[episode_id] = {
            "candidate_count": len(candidates),
            "golden_count": len(golden_entries),
            "golden_good_count": len(good_entries),
            "recall_at_k": recall_at_k,
            "match_details_at_k": match_details_at_k,
            "score_stats": score_stats,
            "timeline_coverage": coverage,
            "n_composite": n_composite,
            "audio_track_candidate_count": audio_track_candidate_count,
            "embedding_used_candidate_count": embedding_used_candidate_count,
            "track_distribution": track_distribution,
            "quality_distribution": _quality_distribution(golden_entries),
            "failure_type_distribution": _failure_type_distribution(golden_entries),
        }

    return results


def _print_report(results: dict[str, dict]) -> None:
    print("\n=== 후보 품질 평가 보고서 ===\n")
    for episode_id, stats in results.items():
        print(f"에피소드: {episode_id}")
        if "error" in stats:
            print(f"  오류: {stats['error']}")
            continue
        print(f"  후보 수: {stats['candidate_count']}  (golden: {stats['golden_count']}, good: {stats['golden_good_count']})")
        for key, val in stats["recall_at_k"].items():
            print(f"  {key}: {val:.1%}")
        sc = stats["score_stats"]
        print(f"  점수 — 평균: {sc['mean']:.2f}, std: {sc['std']:.2f}, top3_avg: {sc['top3_avg']:.2f}")
        print(f"  타임라인 커버리지: {stats['timeline_coverage']:.1%}")
        print(f"  복합 후보 수: {stats['n_composite']}")
        print(f"  오디오 트랙 후보 수: {stats.get('audio_track_candidate_count', 'N/A')}")
        print(f"  임베딩 시그널 사용 후보 수: {stats.get('embedding_used_candidate_count', 'N/A')}")
        track_dist = stats.get("track_distribution", {})
        if track_dist:
            print(f"  트랙별 분포: {track_dist}")
        quality_dist = stats.get("quality_distribution", {})
        if quality_dist:
            print(f"  품질 분포: {quality_dist}")
        failure_dist = stats.get("failure_type_distribution", {})
        if failure_dist:
            print(f"  실패 유형 분포: {failure_dist}")

        # 매칭 상세 (recall@14 기준)
        details = stats.get("match_details_at_k", {}).get("recall@14", [])
        if details:
            unmatched = [d for d in details if not d["matched"]]
            if unmatched:
                print("  미매칭 golden 후보:")
                for d in unmatched:
                    print(f"    - {d['golden_label']} ({d['golden_start']:.1f}–{d['golden_end']:.1f}s, best_iou={d['best_iou']:.2f})")
        print()


def _create_golden_template(
    episode_ids: list[str],
    output_path: Path,
    db: Session | None = None,
) -> None:
    """golden_candidates.json v2 템플릿을 생성한다.

    DB 연결이 있으면 기존 후보를 seed로 사용해 태깅 작업을 용이하게 한다.
    """
    episodes_data: dict[str, dict] = {}
    for ep_id in episode_ids:
        candidates_list: list[dict[str, float | str | list[str]]] = []
        if db is not None:
            rows = list(
                db.scalars(
                    select(Candidate)
                    .where(Candidate.episode_id == ep_id)
                    .order_by(Candidate.total_score.desc())
                )
            )
            for c in rows:
                meta = c.metadata_json if isinstance(c.metadata_json, dict) else {}
                candidates_list.append({
                    "start_time": round(float(c.start_time), 1),
                    "end_time": round(float(c.end_time), 1),
                    "label": c.title_hint or f"후보 #{c.candidate_index}",
                    "quality": "good",
                    "failure_types": [],
                    "notes": f"score={c.total_score:.2f}, track={meta.get('candidate_track', 'dialogue')}",
                })
        if not candidates_list:
            candidates_list.append({
                "start_time": 0.0,
                "end_time": 60.0,
                "label": "좋은 후보 예시 — 실제 값으로 교체하세요",
                "quality": "good",
                "failure_types": [],
                "notes": "",
            })

        episode_title = ""
        if db is not None:
            ep = db.get(Episode, ep_id)
            if ep is not None:
                episode_title = f"{ep.show_title} S{ep.season_number or '?'}E{ep.episode_number or '?'}"

        episodes_data[ep_id] = {
            "title": episode_title,
            "candidates": candidates_list,
        }

    template = {
        "version": 2,
        "description": "Golden set — quality 필드를 good/acceptable/bad로, failure_types를 §6.1 기준으로 태깅하세요.",
        "failure_type_reference": FAILURE_TYPES,
        "episodes": episodes_data,
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    print(f"템플릿 저장됨: {output_path} ({len(episode_ids)}개 에피소드)")


def _export_candidates(
    db: Session,
    episode_ids: list[str],
    output_path: Path,
) -> None:
    """DB에서 후보 목록을 JSON으로 내보내기 (golden seed 용도)."""
    episodes_data: dict[str, dict] = {}
    for ep_id in episode_ids:
        ep = db.get(Episode, ep_id)
        rows = list(
            db.scalars(
                select(Candidate)
                .where(Candidate.episode_id == ep_id)
                .order_by(Candidate.total_score.desc())
            )
        )
        candidates_out: list[dict[str, float | str | int | dict[str, float]]] = []
        for c in rows:
            meta = c.metadata_json if isinstance(c.metadata_json, dict) else {}
            candidates_out.append({
                "candidate_index": c.candidate_index,
                "start_time": round(float(c.start_time), 3),
                "end_time": round(float(c.end_time), 3),
                "duration_seconds": round(float(c.duration_seconds), 3),
                "total_score": round(float(c.total_score), 3),
                "title_hint": c.title_hint,
                "candidate_track": str(meta.get("candidate_track", "dialogue")),
                "arc_form": str(meta.get("arc_form", "contiguous")),
                "window_reason": str(meta.get("window_reason", "")),
                "transcript_excerpt": str(meta.get("transcript_excerpt", ""))[:200],
                "scores": {k: round(float(v), 3) for k, v in (c.scores_json or {}).items() if isinstance(v, (int, float))},
            })
        episodes_data[ep_id] = {
            "title": f"{ep.show_title} S{ep.season_number or '?'}E{ep.episode_number or '?'}" if ep else "",
            "candidate_count": len(candidates_out),
            "candidates": candidates_out,
        }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(episodes_data, f, ensure_ascii=False, indent=2)
    print(f"후보 내보내기 완료: {output_path} ({len(episode_ids)}개 에피소드)")


def _db_feedback_summary(
    db: Session,
    episode_ids: list[str] | None = None,
) -> dict[str, dict[str, int | float | dict[str, int | float]]]:
    """DB에 저장된 운영 피드백을 집계한다.

    Returns:
        {
            "db_feedback_summary": { ... 전체 집계 ... },
            "db_feedback_by_episode": { ep_id: { ... } }
        }
    """
    # 대상 에피소드 결정
    if episode_ids:
        candidate_filter = Candidate.episode_id.in_(episode_ids)
    else:
        candidate_filter = True  # noqa: E712 — 전체

    candidates = list(
        db.scalars(
            select(Candidate).where(candidate_filter)  # type: ignore[arg-type]
        )
    )
    if not candidates:
        return {"db_feedback_summary": {}, "db_feedback_by_episode": {}}

    cand_by_id: dict[str, Candidate] = {c.id: c for c in candidates}
    cand_ids = list(cand_by_id.keys())

    feedbacks = list(
        db.scalars(
            select(CandidateFeedback)
            .where(CandidateFeedback.candidate_id.in_(cand_ids))
            .order_by(CandidateFeedback.created_at.asc())
        )
    )

    # --- 전체 집계 ---
    total_feedback_count = len(feedbacks)
    action_dist: dict[str, int] = {}
    for fb in feedbacks:
        action_dist[fb.action] = action_dist.get(fb.action, 0) + 1

    # 후보 수준 집계
    selected_candidates = [c for c in candidates if c.selected]
    rejected_candidates = [c for c in candidates if c.status == "rejected"]

    selected_scores = [float(c.total_score) for c in selected_candidates]
    rejected_scores = [float(c.total_score) for c in rejected_candidates]

    # failure_tags 분포 (후보의 현재 failure_tags 기반)
    failure_tag_dist: dict[str, int] = {}
    for c in candidates:
        for tag in (c.failure_tags or []):
            failure_tag_dist[str(tag)] = failure_tag_dist.get(str(tag), 0) + 1

    # 트랙별 selected/rejected 분포
    def _track_dist(cands: list[Candidate]) -> dict[str, int]:
        dist: dict[str, int] = {}
        for c in cands:
            meta = c.metadata_json if isinstance(c.metadata_json, dict) else {}
            track = str(meta.get("candidate_track", "dialogue"))
            dist[track] = dist.get(track, 0) + 1
        return dist

    # arc_form별 rejection 분포
    def _field_dist(cands: list[Candidate], field: str) -> dict[str, int]:
        dist: dict[str, int] = {}
        for c in cands:
            meta = c.metadata_json if isinstance(c.metadata_json, dict) else {}
            val = str(meta.get(field, "unknown"))
            dist[val] = dist.get(val, 0) + 1
        return dist

    summary: dict[str, int | float | dict[str, int | float]] = {
        "feedback_count": total_feedback_count,
        "feedback_action_distribution": action_dist,
        "candidate_count": len(candidates),
        "selected_count": len(selected_candidates),
        "rejected_count": len(rejected_candidates),
        "selected_avg_score": round(mean(selected_scores), 3) if selected_scores else 0.0,
        "rejected_avg_score": round(mean(rejected_scores), 3) if rejected_scores else 0.0,
        "failure_tag_distribution": failure_tag_dist,
        "selected_track_distribution": _track_dist(selected_candidates),
        "rejected_track_distribution": _track_dist(rejected_candidates),
        "rejected_arc_form_distribution": _field_dist(rejected_candidates, "arc_form"),
        "rejected_window_reason_distribution": _field_dist(rejected_candidates, "window_reason"),
    }

    # --- 에피소드별 집계 ---
    by_episode: dict[str, dict[str, int | float | dict[str, int]]] = {}
    ep_cands: dict[str, list[Candidate]] = {}
    for c in candidates:
        ep_cands.setdefault(c.episode_id, []).append(c)

    ep_feedbacks: dict[str, list[CandidateFeedback]] = {}
    for fb in feedbacks:
        cand = cand_by_id.get(fb.candidate_id)
        if cand:
            ep_feedbacks.setdefault(cand.episode_id, []).append(fb)

    for ep_id, ep_candidates in ep_cands.items():
        ep_fb = ep_feedbacks.get(ep_id, [])
        ep_selected = [c for c in ep_candidates if c.selected]
        ep_rejected = [c for c in ep_candidates if c.status == "rejected"]
        ep_sel_scores = [float(c.total_score) for c in ep_selected]
        ep_rej_scores = [float(c.total_score) for c in ep_rejected]

        ep_action_dist: dict[str, int] = {}
        for fb in ep_fb:
            ep_action_dist[fb.action] = ep_action_dist.get(fb.action, 0) + 1

        ep_failure_dist: dict[str, int] = {}
        for c in ep_candidates:
            for tag in (c.failure_tags or []):
                ep_failure_dist[str(tag)] = ep_failure_dist.get(str(tag), 0) + 1

        by_episode[ep_id] = {
            "candidate_count": len(ep_candidates),
            "selected_candidate_count": len(ep_selected),
            "rejected_candidate_count": len(ep_rejected),
            "feedback_count": len(ep_fb),
            "feedback_action_distribution": ep_action_dist,
            "candidate_failure_tag_distribution": ep_failure_dist,
            "selected_avg_score": round(mean(ep_sel_scores), 3) if ep_sel_scores else 0.0,
            "rejected_avg_score": round(mean(ep_rej_scores), 3) if ep_rej_scores else 0.0,
            "selected_track_distribution": _track_dist(ep_selected),
            "rejected_track_distribution": _track_dist(ep_rejected),
        }

    return {
        "db_feedback_summary": summary,
        "db_feedback_by_episode": by_episode,
    }


def _print_feedback_report(feedback_data: dict[str, dict[str, int | float | dict[str, int | float]]]) -> None:
    summary = feedback_data.get("db_feedback_summary", {})
    if not summary:
        print("  (DB 피드백 데이터 없음)")
        return

    print("\n=== DB 운영 피드백 집계 ===\n")
    print(f"  총 피드백 수: {summary.get('feedback_count', 0)}")
    print(f"  후보 수: {summary.get('candidate_count', 0)}")
    print(f"  채택: {summary.get('selected_count', 0)}, 탈락: {summary.get('rejected_count', 0)}")
    print(f"  채택 평균 점수: {summary.get('selected_avg_score', 0):.2f}")
    print(f"  탈락 평균 점수: {summary.get('rejected_avg_score', 0):.2f}")

    action_dist = summary.get("feedback_action_distribution", {})
    if action_dist:
        print(f"  액션 분포: {action_dist}")
    fail_dist = summary.get("failure_tag_distribution", {})
    if fail_dist:
        print(f"  실패 유형 분포: {fail_dist}")
    rej_track = summary.get("rejected_track_distribution", {})
    if rej_track:
        print(f"  탈락 트랙 분포: {rej_track}")
    rej_arc = summary.get("rejected_arc_form_distribution", {})
    if rej_arc:
        print(f"  탈락 arc_form 분포: {rej_arc}")
    rej_reason = summary.get("rejected_window_reason_distribution", {})
    if rej_reason:
        print(f"  탈락 window_reason 분포: {rej_reason}")

    by_ep = feedback_data.get("db_feedback_by_episode", {})
    if by_ep:
        print(f"\n  에피소드별 ({len(by_ep)}개):")
        for ep_id, ep_stats in by_ep.items():
            sel = ep_stats.get("selected_candidate_count", 0)
            rej = ep_stats.get("rejected_candidate_count", 0)
            fb_ct = ep_stats.get("feedback_count", 0)
            print(f"    {ep_id[:12]}… — 채택 {sel}, 탈락 {rej}, 피드백 {fb_ct}건")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="후보 품질 오프라인 평가")
    parser.add_argument("--golden", type=Path, default=None, help="golden_candidates.json 경로")
    parser.add_argument("--db", type=str, default=None, help="DATABASE_URL 오버라이드")
    parser.add_argument("--episode-ids", nargs="*", help="평가할 에피소드 ID 목록 (생략 시 golden의 전체)")
    parser.add_argument("--top-k", nargs="*", type=int, default=[5, 10, 14], help="Recall@K 값들")
    parser.add_argument("--iou-threshold", type=float, default=0.3, help="IOU 매칭 임계값 (기본 0.3)")
    parser.add_argument("--output", type=Path, default=None, help="JSON 결과 저장 경로")
    parser.add_argument(
        "--include-db-feedback",
        action="store_true",
        default=False,
        help="DB에 저장된 운영 피드백 집계를 함께 출력",
    )
    parser.add_argument(
        "--create-golden-template",
        type=Path,
        default=None,
        metavar="PATH",
        help="golden JSON v2 템플릿 생성 (DB 후보를 seed로 사용)",
    )
    parser.add_argument(
        "--export-candidates",
        type=Path,
        default=None,
        metavar="PATH",
        help="DB에서 후보 목록을 JSON으로 내보내기",
    )
    args = parser.parse_args()

    database_url = args.db or os.environ.get("DATABASE_URL", "")

    if args.export_candidates:
        if not database_url:
            parser.error("--db 또는 DATABASE_URL 환경변수를 설정해 주세요.")
        ep_ids = args.episode_ids or []
        if not ep_ids:
            parser.error("--export-candidates는 --episode-ids가 필요합니다.")
        engine = create_engine(database_url)
        with Session(engine) as db:
            _export_candidates(db, ep_ids, args.export_candidates)
        return

    if args.create_golden_template:
        ep_ids = args.episode_ids or ["episode_id_here"]
        if database_url:
            engine = create_engine(database_url)
            with Session(engine) as db:
                _create_golden_template(ep_ids, args.create_golden_template, db)
        else:
            _create_golden_template(ep_ids, args.create_golden_template)
        return

    # --include-db-feedback만 사용 시 golden 없어도 동작
    if args.include_db_feedback and not args.golden:
        if not database_url:
            parser.error("--db 또는 DATABASE_URL 환경변수를 설정해 주세요.")
        engine = create_engine(database_url)
        with Session(engine) as db:
            feedback_data = _db_feedback_summary(db, episode_ids=args.episode_ids)
        _print_feedback_report(feedback_data)
        if args.output:
            with args.output.open("w", encoding="utf-8") as f:
                json.dump(feedback_data, f, ensure_ascii=False, indent=2)
            print(f"결과 저장됨: {args.output}")
        return

    if not args.golden or not args.golden.is_file():
        parser.error("--golden 인자로 golden_candidates.json 경로를 지정해 주세요.")

    if not database_url:
        parser.error("--db 또는 DATABASE_URL 환경변수를 설정해 주세요.")

    golden = _load_golden(args.golden)
    engine = create_engine(database_url)

    with Session(engine) as db:
        results = evaluate_pipeline(
            db,
            golden,
            episode_ids=args.episode_ids,
            top_ks=tuple(args.top_k),
            iou_threshold=args.iou_threshold,
        )
        feedback_data: dict[str, dict[str, int | float | dict[str, int | float]]] = {}
        if args.include_db_feedback:
            feedback_data = _db_feedback_summary(db, episode_ids=args.episode_ids)

    _print_report(results)
    if feedback_data:
        _print_feedback_report(feedback_data)

    if args.output:
        output_data: dict[str, dict[str, int | float | dict[str, int | float]] | dict[str, dict[str, float | str | bool | int | list[dict[str, str | float | bool]]]]] = {**results}
        if feedback_data:
            output_data.update(feedback_data)
        with args.output.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        print(f"결과 저장됨: {args.output}")


if __name__ == "__main__":
    main()
