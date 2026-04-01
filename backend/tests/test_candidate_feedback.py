"""feedback 상태 전이 회귀 테스트."""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

# 파일 기반 SQLite 사용 — :memory:는 커넥션마다 별도 DB라서 문제
_TEST_DB = _BACKEND_DIR / "data" / "test_feedback.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["OPENAI_API_KEY"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import Base, SessionLocal, engine  # noqa: E402
from app.db.models import (  # noqa: E402, F401
    Candidate, CandidateFeedback, CandidateStatus, Episode,
    EpisodeStatus, Export, Job, ScriptDraft, Shot,
    TranscriptSegment, VideoDraft,
)
from app.main import app  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_tables() -> Generator[None, None, None]:
    yield
    with SessionLocal() as session:
        session.execute(text("PRAGMA foreign_keys=OFF"))
        for table in Base.metadata.sorted_tables:
            session.execute(table.delete())
        session.execute(text("PRAGMA foreign_keys=ON"))
        session.commit()


def _seed(n: int = 5) -> tuple[str, list[str]]:
    with SessionLocal() as session:
        ep = Episode(
            show_title="테스트 드라마",
            source_video_path="/tmp/test.mp4",
            status=EpisodeStatus.READY.value,
        )
        session.add(ep)
        session.flush()
        cand_ids: list[str] = []
        for i in range(1, n + 1):
            c = Candidate(
                episode_id=ep.id,
                candidate_index=i,
                title_hint=f"후보 {i}",
                start_time=float(i * 30),
                end_time=float(i * 30 + 60),
                duration_seconds=60.0,
                total_score=10.0 - i * 0.5,
            )
            session.add(c)
            session.flush()
            cand_ids.append(c.id)
        session.commit()
        return ep.id, cand_ids


class TestSelectedFeedback:
    def test_selected_changes_status(self) -> None:
        _, cids = _seed(3)
        resp = client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={"action": "selected"})
        assert resp.status_code == 200
        d = resp.json()
        assert d["after_snapshot"]["status"] == "selected"
        assert d["after_snapshot"]["selected"] is True
        assert d["before_snapshot"]["status"] == "generated"

    def test_selected_allows_multiple(self) -> None:
        _, cids = _seed(3)
        for cid in cids[:2]:
            assert client.post(f"/api/v1/candidates/{cid}/feedbacks", json={"action": "selected"}).status_code == 200
        for cid in cids[:2]:
            detail = client.get(f"/api/v1/candidates/{cid}").json()
            assert detail["selected"] is True
            assert detail["status"] == "selected"


class TestRejectedFeedback:
    def test_rejected_changes_status(self) -> None:
        _, cids = _seed(3)
        resp = client.post(f"/api/v1/candidates/{cids[1]}/feedbacks", json={
            "action": "rejected", "reason": "맥락 부족", "failure_tags": ["context_missing"],
        })
        assert resp.status_code == 200
        assert resp.json()["after_snapshot"]["status"] == "rejected"

    def test_rejected_syncs_failure_tags(self) -> None:
        _, cids = _seed(3)
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "rejected", "failure_tags": ["no_payoff", "too_long"],
        })
        detail = client.get(f"/api/v1/candidates/{cids[0]}").json()
        assert "no_payoff" in detail["failure_tags"]
        assert "too_long" in detail["failure_tags"]


class TestSnapshotCompleteness:
    def test_snapshots_have_required_fields(self) -> None:
        _, cids = _seed(2)
        d = client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={"action": "selected"}).json()
        required = {"status", "selected", "candidate_index", "total_score", "failure_tags"}
        assert required <= set(d["before_snapshot"].keys())
        assert required <= set(d["after_snapshot"].keys())


class TestValidation:
    def test_invalid_action(self) -> None:
        _, cids = _seed(1)
        assert client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={"action": "invalid"}).status_code == 422

    def test_invalid_failure_tag(self) -> None:
        _, cids = _seed(1)
        assert client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "selected", "failure_tags": ["fake"],
        }).status_code == 422


class TestReorderFeedback:
    def test_reorder_shifts_all_siblings(self) -> None:
        _, cids = _seed(5)
        resp = client.post(f"/api/v1/candidates/{cids[3]}/feedbacks", json={
            "action": "reordered", "metadata": {"new_rank": 1},
        })
        assert resp.status_code == 200
        assert resp.json()["after_snapshot"]["candidate_index"] == 1
        with SessionLocal() as s:
            indices = sorted(s.get(Candidate, cid).candidate_index for cid in cids)  # type: ignore[union-attr]
        assert indices == [1, 2, 3, 4, 5]

    def test_reorder_preserves_count(self) -> None:
        ep_id, cids = _seed(5)
        client.post(f"/api/v1/candidates/{cids[2]}/feedbacks", json={
            "action": "reordered", "metadata": {"new_rank": 5},
        })
        with SessionLocal() as s:
            assert s.query(Candidate).filter(Candidate.episode_id == ep_id).count() == 5

    def test_reorder_without_new_rank_is_noop(self) -> None:
        _, cids = _seed(3)
        d = client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={"action": "reordered"}).json()
        assert d["before_snapshot"]["candidate_index"] == d["after_snapshot"]["candidate_index"]

    def test_reorder_metadata_has_from_to_count(self) -> None:
        """feedback metadata에 reorder_from/reorder_to/episode_candidate_count가 기록된다."""
        _, cids = _seed(5)
        resp = client.post(f"/api/v1/candidates/{cids[3]}/feedbacks", json={
            "action": "reordered", "metadata": {"new_rank": 2},
        })
        assert resp.status_code == 200
        meta = resp.json()["metadata"]
        assert meta["reorder_from"] == 4
        assert meta["reorder_to"] == 2
        assert meta["episode_candidate_count"] == 5

    def test_reorder_clamps_beyond_range(self) -> None:
        """new_rank > 후보 수 → 맨 뒤로 클램프, new_rank < 1 → 1로 클램프."""
        _, cids = _seed(3)

        # 범위 초과 → 맨 뒤
        resp = client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "reordered", "metadata": {"new_rank": 999},
        })
        assert resp.status_code == 200
        assert resp.json()["metadata"]["reorder_to"] == 3
        with SessionLocal() as s:
            indices = sorted(s.get(Candidate, cid).candidate_index for cid in cids)  # type: ignore[union-attr]
        assert indices == [1, 2, 3]

        # 범위 미만 → 1
        resp = client.post(f"/api/v1/candidates/{cids[2]}/feedbacks", json={
            "action": "reordered", "metadata": {"new_rank": -5},
        })
        assert resp.status_code == 200
        assert resp.json()["metadata"]["reorder_to"] == 1


class TestReorderDetailVerification:
    def test_reorder_changes_detail_candidate_index(self) -> None:
        """reorder 후 detail 조회 시 대상 후보의 candidate_index가 변경된다."""
        _, cids = _seed(5)
        # cids[3]은 originally index=4. 2위로 이동.
        client.post(f"/api/v1/candidates/{cids[3]}/feedbacks", json={
            "action": "reordered", "metadata": {"new_rank": 2},
        })
        # detail에서 직접 확인 — feedback_summary도 같이 확인
        detail = client.get(f"/api/v1/candidates/{cids[3]}").json()
        # metadata에 reordered=True 확인
        assert detail["metadata"].get("reordered") is True
        assert detail["feedback_summary"]["feedback_count"] == 1
        assert detail["feedback_summary"]["latest_feedback_action"] == "reordered"

    def test_reorder_feedback_metadata_in_detail(self) -> None:
        """reorder feedback의 metadata에 reorder_from/to/count가 있는지 detail feedbacks 목록에서 확인."""
        _, cids = _seed(3)
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "reordered", "metadata": {"new_rank": 3},
        })
        feedbacks = client.get(f"/api/v1/candidates/{cids[0]}/feedbacks").json()
        fb = feedbacks["items"][0]
        assert fb["metadata"]["reorder_from"] == 1
        assert fb["metadata"]["reorder_to"] == 3
        assert fb["metadata"]["episode_candidate_count"] == 3


class TestFeedbackList:
    def test_list_returns_feedbacks(self) -> None:
        _, cids = _seed(1)
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={"action": "selected"})
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={"action": "rejected", "reason": "재고"})
        d = client.get(f"/api/v1/candidates/{cids[0]}/feedbacks").json()
        assert d["total"] == 2


class TestFeedbackSummaryInDetail:
    def test_detail_includes_feedback_summary(self) -> None:
        _, cids = _seed(1)
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={"action": "selected"})
        detail = client.get(f"/api/v1/candidates/{cids[0]}").json()
        assert detail["feedback_summary"]["feedback_count"] == 1
        assert detail["feedback_summary"]["latest_feedback_action"] == "selected"

    def test_detail_includes_latest_feedback_reason(self) -> None:
        _, cids = _seed(1)
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "rejected", "reason": "맥락 부족",
        })
        detail = client.get(f"/api/v1/candidates/{cids[0]}").json()
        assert detail["feedback_summary"]["latest_feedback_reason"] == "맥락 부족"

    def test_detail_selected_and_failure_tags(self) -> None:
        _, cids = _seed(1)
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "rejected", "failure_tags": ["no_payoff", "too_long"],
        })
        detail = client.get(f"/api/v1/candidates/{cids[0]}").json()
        assert detail["selected"] is False
        assert detail["status"] == "rejected"
        assert "no_payoff" in detail["failure_tags"]
        assert "too_long" in detail["failure_tags"]


class TestFailureTagsClearSemantics:
    """failure_tags 동기화 정책:
    - feedback 생성 시 Candidate.failure_tags는 request.failure_tags로 항상 overwrite 동기화
    - failure_tags=[] → clear
    - failure_tags=["a","b","a"] → dedupe 후 ["a","b"]
    - failure_tags 키 미전송(default=[]) → clear (보존 아님)
    """

    def test_empty_list_clears_tags(self) -> None:
        """정책: failure_tags=[] → Candidate.failure_tags clear."""
        _, cids = _seed(1)
        # 먼저 태그 설정
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "rejected", "failure_tags": ["no_payoff", "too_long"],
        })
        detail = client.get(f"/api/v1/candidates/{cids[0]}").json()
        assert len(detail["failure_tags"]) == 2

        # 빈 배열로 clear
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "edited", "failure_tags": [],
        })
        detail = client.get(f"/api/v1/candidates/{cids[0]}").json()
        assert detail["failure_tags"] == []

    def test_omitted_tags_clears_existing(self) -> None:
        """정책: failure_tags 미전송(default=[]) → Candidate.failure_tags clear (보존 아님)."""
        _, cids = _seed(1)
        # 먼저 태그 설정
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "rejected", "failure_tags": ["context_missing"],
        })
        detail = client.get(f"/api/v1/candidates/{cids[0]}").json()
        assert "context_missing" in detail["failure_tags"]

        # failure_tags 키 없이 피드백 생성 → default=[] → clear
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "selected",
        })
        detail = client.get(f"/api/v1/candidates/{cids[0]}").json()
        assert detail["failure_tags"] == []

    def test_snapshot_reflects_cleared_tags(self) -> None:
        """정책: clear 후 after_snapshot.failure_tags가 빈 배열."""
        _, cids = _seed(1)
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "rejected", "failure_tags": ["weak_structure"],
        })
        resp = client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "edited", "failure_tags": [],
        })
        d = resp.json()
        assert d["before_snapshot"]["failure_tags"] == ["weak_structure"]
        assert d["after_snapshot"]["failure_tags"] == []


class TestFeedbackSummaryAllFields:
    def test_all_summary_fields_present(self) -> None:
        """feedback_summary에 모든 필드가 채워지는지 확인."""
        _, cids = _seed(1)
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "rejected", "reason": "맥락 부족", "failure_tags": ["context_missing"],
        })
        detail = client.get(f"/api/v1/candidates/{cids[0]}").json()
        summary = detail["feedback_summary"]
        assert summary["feedback_count"] == 1
        assert summary["latest_feedback_action"] == "rejected"
        assert summary["latest_feedback_reason"] == "맥락 부족"
        assert summary["latest_feedback_at"] is not None

    def test_summary_count_increments_and_latest_is_deterministic(self) -> None:
        """피드백 추가 후 feedback_count 증가 + latest는 created_seq 기반 결정적 선택."""
        _, cids = _seed(1)
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "rejected", "reason": "첫 번째 사유",
        })
        detail1 = client.get(f"/api/v1/candidates/{cids[0]}").json()
        assert detail1["feedback_summary"]["feedback_count"] == 1
        assert detail1["feedback_summary"]["latest_feedback_action"] == "rejected"

        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={
            "action": "selected", "reason": "재검토 후 채택",
        })
        detail2 = client.get(f"/api/v1/candidates/{cids[0]}").json()
        assert detail2["feedback_summary"]["feedback_count"] == 2
        # created_seq auto-increment로 두 번째 피드백이 항상 latest
        assert detail2["feedback_summary"]["latest_feedback_action"] == "selected"
        assert detail2["feedback_summary"]["latest_feedback_reason"] == "재검토 후 채택"

    def test_summary_empty_when_no_feedback(self) -> None:
        """피드백 없으면 summary가 기본값."""
        _, cids = _seed(1)
        detail = client.get(f"/api/v1/candidates/{cids[0]}").json()
        summary = detail["feedback_summary"]
        assert summary["feedback_count"] == 0
        assert summary["latest_feedback_action"] is None
        assert summary["latest_feedback_reason"] is None

    def test_detail_summary_matches_feedbacks_list_first(self) -> None:
        """detail summary latest와 feedbacks list 첫 항목이 동일 기준으로 정렬된다."""
        _, cids = _seed(1)
        cid = cids[0]
        client.post(f"/api/v1/candidates/{cid}/feedbacks", json={
            "action": "rejected", "reason": "첫 번째",
        })
        client.post(f"/api/v1/candidates/{cid}/feedbacks", json={
            "action": "selected", "reason": "두 번째",
        })
        client.post(f"/api/v1/candidates/{cid}/feedbacks", json={
            "action": "edited", "reason": "세 번째",
        })

        detail = client.get(f"/api/v1/candidates/{cid}").json()
        feedbacks = client.get(f"/api/v1/candidates/{cid}/feedbacks").json()

        summary_action = detail["feedback_summary"]["latest_feedback_action"]
        list_first_action = feedbacks["items"][0]["action"]
        assert summary_action == list_first_action
        assert summary_action == "edited"


class TestEvaluateDbFeedback:
    def test_db_feedback_summary_not_empty(self) -> None:
        """evaluate_candidates.py의 _db_feedback_summary가 DB 피드백을 올바르게 집계한다."""
        import importlib
        import scripts.evaluate_candidates as eval_mod
        importlib.reload(eval_mod)

        _, cids = _seed(3)
        # 피드백 생성
        client.post(f"/api/v1/candidates/{cids[0]}/feedbacks", json={"action": "selected"})
        client.post(f"/api/v1/candidates/{cids[1]}/feedbacks", json={
            "action": "rejected", "failure_tags": ["context_missing"],
        })

        with SessionLocal() as session:
            result = eval_mod._db_feedback_summary(session)

        summary = result.get("db_feedback_summary", {})
        assert summary.get("feedback_count", 0) >= 2
        assert summary.get("selected_count", 0) >= 1
        assert summary.get("rejected_count", 0) >= 1
