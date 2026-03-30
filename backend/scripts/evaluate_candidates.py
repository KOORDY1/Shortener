#!/usr/bin/env python3
"""오프라인 후보 품질 평가 스크립트.

golden_candidates.json(사람이 선별한 정답 후보)과 파이프라인 출력을
비교해 Recall@K, 점수 분포, 타임라인 커버리지를 계산한다.

사용법:
    python scripts/evaluate_candidates.py \\
        --golden golden_candidates.json \\
        --db sqlite:///data/app.db \\
        [--episode-ids ep1 ep2] \\
        [--top-k 5 10 14]

golden_candidates.json 형식:
    {
      "<episode_id>": [
        {"start_time": 100.0, "end_time": 160.0, "label": "좋은 후보 1"},
        ...
      ],
      ...
    }
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from statistics import mean, stdev
from typing import NamedTuple

# 프로젝트 루트를 sys.path에 추가
_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

os.environ.setdefault("DATABASE_URL", f"sqlite:///{_BACKEND_DIR / 'data' / 'app.db'}")
os.environ.setdefault("CELERY_TASK_ALWAYS_EAGER", "true")
os.environ.setdefault("OPENAI_API_KEY", "")

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.models import Candidate  # noqa: E402


class GoldenEntry(NamedTuple):
    start_time: float
    end_time: float
    label: str


def _load_golden(path: Path) -> dict[str, list[GoldenEntry]]:
    with path.open(encoding="utf-8") as f:
        raw: dict[str, list[dict]] = json.load(f)
    result: dict[str, list[GoldenEntry]] = {}
    for episode_id, entries in raw.items():
        result[episode_id] = [
            GoldenEntry(
                start_time=float(e.get("start_time", 0.0)),
                end_time=float(e.get("end_time", 0.0)),
                label=str(e.get("label", "")),
            )
            for e in entries
        ]
    return result


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
) -> float:
    """Top-K 후보 중 golden과 IOU ≥ threshold로 매칭되는 비율."""
    if not golden:
        return 0.0
    top_k = candidates[:k]
    matched = 0
    for entry in golden:
        for cand in top_k:
            iou = _temporal_iou(
                float(cand.start_time), float(cand.end_time),
                entry.start_time, entry.end_time,
            )
            if iou >= iou_threshold:
                matched += 1
                break
    return matched / len(golden)


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


def evaluate_pipeline(
    db: Session,
    golden: dict[str, list[GoldenEntry]],
    episode_ids: list[str] | None = None,
    top_ks: tuple[int, ...] = (5, 10, 14),
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
        scores = [float(c.total_score) for c in candidates]

        recall_at_k: dict[str, float] = {}
        for k in top_ks:
            recall_at_k[f"recall@{k}"] = round(_recall_at_k(candidates, golden_entries, k=k), 3)

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

        results[episode_id] = {
            "candidate_count": len(candidates),
            "golden_count": len(golden_entries),
            "recall_at_k": recall_at_k,
            "score_stats": score_stats,
            "timeline_coverage": coverage,
            "n_composite": n_composite,
        }

    return results


def _print_report(results: dict[str, dict]) -> None:
    print("\n=== 후보 품질 평가 보고서 ===\n")
    for episode_id, stats in results.items():
        print(f"에피소드: {episode_id}")
        if "error" in stats:
            print(f"  오류: {stats['error']}")
            continue
        print(f"  후보 수: {stats['candidate_count']}  (golden: {stats['golden_count']})")
        for key, val in stats["recall_at_k"].items():
            print(f"  {key}: {val:.1%}")
        sc = stats["score_stats"]
        print(f"  점수 — 평균: {sc['mean']:.2f}, std: {sc['std']:.2f}, top3_avg: {sc['top3_avg']:.2f}")
        print(f"  타임라인 커버리지: {stats['timeline_coverage']:.1%}")
        print(f"  복합 후보 수: {stats['n_composite']}")
        print()


def _create_golden_template(episode_ids: list[str], output_path: Path) -> None:
    """golden_candidates.json 초기 템플릿을 생성한다."""
    template: dict[str, list[dict]] = {
        ep_id: [
            {"start_time": 0.0, "end_time": 60.0, "label": "좋은 후보 예시 — 실제 값으로 교체하세요"}
        ]
        for ep_id in episode_ids
    }
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(template, f, ensure_ascii=False, indent=2)
    print(f"템플릿 저장됨: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="후보 품질 오프라인 평가")
    parser.add_argument("--golden", type=Path, default=None, help="golden_candidates.json 경로")
    parser.add_argument("--db", type=str, default=None, help="DATABASE_URL 오버라이드")
    parser.add_argument("--episode-ids", nargs="*", help="평가할 에피소드 ID 목록 (생략 시 golden의 전체)")
    parser.add_argument("--top-k", nargs="*", type=int, default=[5, 10, 14], help="Recall@K 값들")
    parser.add_argument("--output", type=Path, default=None, help="JSON 결과 저장 경로")
    parser.add_argument(
        "--create-golden-template",
        type=Path,
        default=None,
        metavar="PATH",
        help="golden JSON 템플릿을 생성할 경로",
    )
    args = parser.parse_args()

    if args.create_golden_template:
        ep_ids = args.episode_ids or ["episode_id_here"]
        _create_golden_template(ep_ids, args.create_golden_template)
        return

    if not args.golden or not args.golden.is_file():
        parser.error("--golden 인자로 golden_candidates.json 경로를 지정해 주세요.")

    database_url = args.db or os.environ.get("DATABASE_URL", "")
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
        )

    _print_report(results)

    if args.output:
        with args.output.open("w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"결과 저장됨: {args.output}")


if __name__ == "__main__":
    main()
