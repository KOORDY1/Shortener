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
