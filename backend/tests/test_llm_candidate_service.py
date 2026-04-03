"""LLM 후보 추천 서비스 단위 테스트."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
os.environ["OPENAI_API_KEY"] = ""

from app.services.llm_candidate_service import (
    LlmSuggestion,
    VerifyResult,
    _build_few_shot_examples,
    _build_system_prompt,
    _cache_key,
    _detect_foreign_scene_gaps,
    _format_transcript_for_llm,
    _parse_llm_response,
    _parse_verify_response,
    _read_cache,
    _snap_end_to_sentence_boundary,
    _snap_to_shot_boundaries,
    _write_cache,
    llm_suggestions_to_scored_windows,
    suggest_candidates_with_llm,
    verify_candidates_with_llm,
)


class _FakeSegment:
    """TranscriptSegment 대용 — ORM 없이 속성만 제공."""
    def __init__(self, start_time: float, end_time: float, text: str) -> None:
        self.start_time = start_time
        self.end_time = end_time
        self.text = text
        self.speaker_label: str | None = None


class _FakeShot:
    """Shot 대용 — ORM 없이 속성만 제공."""
    def __init__(self, start_time: float, end_time: float) -> None:
        self.start_time = start_time
        self.end_time = end_time


# type: ignore — Fake 클래스는 ORM 모델과 구조적으로 호환
_make_segment = _FakeSegment  # type: ignore[assignment]
_make_shot = _FakeShot  # type: ignore[assignment]


class TestFormatTranscript:
    def test_formats_segments_with_timestamps(self) -> None:
        segments = [
            _make_segment(0.0, 5.0, "안녕하세요"),
            _make_segment(5.0, 10.0, "반갑습니다"),
        ]
        result = _format_transcript_for_llm(segments)
        assert "[0.0–5.0] 안녕하세요" in result
        assert "[5.0–10.0] 반갑습니다" in result

    def test_skips_empty_text(self) -> None:
        segments = [
            _make_segment(0.0, 5.0, ""),
            _make_segment(5.0, 10.0, "텍스트"),
        ]
        result = _format_transcript_for_llm(segments)
        assert "[0.0–5.0]" not in result
        assert "[5.0–10.0] 텍스트" in result


class TestParseLlmResponse:
    def test_parses_valid_json(self) -> None:
        content = '{"candidates": [{"start_time": 10.0, "end_time": 50.0, "title": "테스트", "reason": "좋음", "score": 8.5}]}'
        result = _parse_llm_response(content)
        assert len(result) == 1
        assert result[0].start_time == 10.0
        assert result[0].end_time == 50.0
        assert result[0].title == "테스트"
        assert result[0].score == 8.5

    def test_parses_wrapped_json(self) -> None:
        content = '```json\n{"candidates": [{"start_time": 10.0, "end_time": 50.0, "title": "t", "reason": "r", "score": 7}]}\n```'
        result = _parse_llm_response(content)
        assert len(result) == 1

    def test_clamps_score(self) -> None:
        content = '{"candidates": [{"start_time": 0, "end_time": 60, "title": "", "reason": "", "score": 15}]}'
        result = _parse_llm_response(content)
        assert result[0].score == 10.0

    def test_filters_invalid_range(self) -> None:
        content = '{"candidates": [{"start_time": 50, "end_time": 30, "title": "", "reason": "", "score": 5}]}'
        result = _parse_llm_response(content)
        assert len(result) == 0

    def test_handles_malformed_json(self) -> None:
        result = _parse_llm_response("not json")
        assert result == []

    def test_handles_empty_candidates(self) -> None:
        result = _parse_llm_response('{"candidates": []}')
        assert result == []


class TestSuggestCandidatesWithLlm:
    def test_returns_empty_without_api_key(self) -> None:
        segments = [_make_segment(0.0, 60.0, "테스트 대사")]
        result = suggest_candidates_with_llm(segments)
        assert result == []

    def test_returns_empty_without_transcript(self) -> None:
        result = suggest_candidates_with_llm([])
        assert result == []


class TestSnapToShotBoundaries:
    def test_snaps_to_nearest_boundary(self) -> None:
        shots = [_make_shot(0.0, 30.0), _make_shot(30.0, 62.5), _make_shot(62.5, 90.0)]
        start, end = _snap_to_shot_boundaries(31.2, 61.8, shots)  # type: ignore[arg-type]
        assert start == 30.0  # snapped to shot boundary 30.0
        assert end == 62.5  # snapped to shot boundary 62.5

    def test_no_snap_if_too_far(self) -> None:
        shots = [_make_shot(0.0, 10.0), _make_shot(100.0, 110.0)]
        start, end = _snap_to_shot_boundaries(50.0, 80.0, shots)  # type: ignore[arg-type]
        assert start == 50.0  # no boundary within 5s
        assert end == 80.0

    def test_empty_shots_returns_original(self) -> None:
        start, end = _snap_to_shot_boundaries(10.0, 50.0, [])
        assert start == 10.0
        assert end == 50.0


class TestLlmSuggestionsToScoredWindows:
    def test_converts_with_normalized_score(self) -> None:
        suggestions = [
            LlmSuggestion(start_time=10.0, end_time=50.0, title="제목", reason="이유", score=8.0),
        ]
        segments = [_make_segment(10.0, 50.0, "대사 텍스트")]
        windows = llm_suggestions_to_scored_windows(suggestions, segments)  # type: ignore[arg-type]
        assert len(windows) == 1
        w = windows[0]
        assert w.metadata_json["generated_by"] == "llm_candidate_v1"
        assert w.metadata_json["candidate_track"] == "llm"
        assert w.metadata_json["llm_reason"] == "이유"
        assert w.title_hint == "제목"
        # 점수 정규화: 8.0 * 0.85 = 6.8
        assert w.scores_json["llm_score"] == 8.0
        assert w.scores_json["llm_score_normalized"] == 6.8
        assert w.total_score >= 6.8  # visual bonus 가산 가능

    def test_shot_snap_applied(self) -> None:
        suggestions = [
            LlmSuggestion(start_time=31.0, end_time=61.0, title="t", reason="r", score=7.0),
        ]
        segments = [_make_segment(30.0, 62.0, "텍스트")]
        shots = [_make_shot(0.0, 30.0), _make_shot(30.0, 62.5), _make_shot(62.5, 90.0)]
        windows = llm_suggestions_to_scored_windows(suggestions, segments, shots=shots)  # type: ignore[arg-type]
        w = windows[0]
        assert w.start_time == 30.0  # shot snapped from 31.0
        assert w.end_time == 62.0  # shot snapped to 62.5, then sentence snapped to 62.0 (자막 끝)
        assert w.metadata_json["shot_snapped"] is True
        assert w.metadata_json["sentence_snapped"] is True
        assert w.metadata_json["original_start"] == 31.0

    def test_visual_impact_in_scores(self) -> None:
        suggestions = [
            LlmSuggestion(start_time=0.0, end_time=60.0, title="t", reason="r", score=7.0),
        ]
        segments = [_make_segment(0.0, 60.0, "텍스트")]
        shots = [_make_shot(float(i * 5), float(i * 5 + 5)) for i in range(12)]
        windows = llm_suggestions_to_scored_windows(
            suggestions, segments, shots=shots, episode_avg_cut_rate=0.1,  # type: ignore[arg-type]
        )
        assert "visual_impact" in windows[0].scores_json
        assert "speech_coverage" in windows[0].scores_json

    def test_collects_transcript_excerpt(self) -> None:
        suggestions = [
            LlmSuggestion(start_time=0.0, end_time=60.0, title="t", reason="r", score=7.0),
        ]
        segments = [
            _make_segment(5.0, 15.0, "첫 번째"),
            _make_segment(20.0, 30.0, "두 번째"),
            _make_segment(100.0, 110.0, "범위 밖"),
        ]
        windows = llm_suggestions_to_scored_windows(suggestions, segments)  # type: ignore[arg-type]
        excerpt = windows[0].metadata_json["transcript_excerpt"]
        assert "첫 번째" in excerpt
        assert "두 번째" in excerpt
        assert "범위 밖" not in excerpt


class TestBuildSystemPrompt:
    def test_v1_default(self) -> None:
        prompt = _build_system_prompt("v1", "kr_us_drama")
        assert "쇼츠 편집 전문가" in prompt
        assert "드라마" in prompt
        assert "JSON만 반환" in prompt

    def test_v2_variant(self) -> None:
        prompt = _build_system_prompt("v2", "kr_us_drama")
        assert "숏폼 콘텐츠 큐레이터" in prompt
        assert "드라마" in prompt

    def test_variety_genre(self) -> None:
        prompt = _build_system_prompt("v1", "variety")
        assert "예능" in prompt
        assert "웃음" in prompt

    def test_documentary_genre(self) -> None:
        prompt = _build_system_prompt("v1", "documentary")
        assert "다큐" in prompt

    def test_unknown_genre_no_crash(self) -> None:
        prompt = _build_system_prompt("v1", "unknown_channel")
        assert "JSON만 반환" in prompt  # 기본 구조는 유지

    def test_unknown_version_falls_back_to_v1(self) -> None:
        prompt = _build_system_prompt("v999", "kr_us_drama")
        assert "쇼츠 편집 전문가" in prompt


class TestCaching:
    def test_cache_roundtrip(self, tmp_path: Path) -> None:
        """캐시 쓰기→읽기 라운드트립."""
        import app.services.llm_candidate_service as mod
        original_dir = mod._cache_dir

        # 임시 디렉터리로 캐시 경로 교체
        mod._cache_dir = lambda: tmp_path  # type: ignore[assignment]
        try:
            key = _cache_key("test transcript", "v1", "kr_us_drama", "gpt-5.1-mini", 10)
            assert _read_cache(key) is None

            data: list[dict[str, float | str]] = [
                {"start_time": 10.0, "end_time": 50.0, "title": "t", "reason": "r", "score": 8.0}
            ]
            _write_cache(key, data)

            cached = _read_cache(key)
            assert cached is not None
            assert len(cached) == 1
            assert cached[0]["start_time"] == 10.0
        finally:
            mod._cache_dir = original_dir  # type: ignore[assignment]

    def test_cache_key_differs_by_version(self) -> None:
        k1 = _cache_key("same", "v1", "kr_us_drama", "gpt-5.1-mini", 10)
        k2 = _cache_key("same", "v2", "kr_us_drama", "gpt-5.1-mini", 10)
        assert k1 != k2

    def test_cache_key_differs_by_channel(self) -> None:
        k1 = _cache_key("same", "v1", "kr_us_drama", "gpt-5.1-mini", 10)
        k2 = _cache_key("same", "v1", "variety", "gpt-5.1-mini", 10)
        assert k1 != k2


class TestParseVerifyResponse:
    def test_parses_valid_response(self) -> None:
        content = '{"results": [{"index": 0, "keep": true, "adjusted_start": 10.0, "adjusted_end": 50.0, "final_score": 8.0, "reason": "좋음"}]}'
        results = _parse_verify_response(content)
        assert len(results) == 1
        assert results[0].keep is True
        assert results[0].final_score == 8.0

    def test_parses_drop(self) -> None:
        content = '{"results": [{"index": 0, "keep": false, "adjusted_start": 0, "adjusted_end": 0, "final_score": 3.0, "reason": "맥락 부족"}]}'
        results = _parse_verify_response(content)
        assert results[0].keep is False

    def test_handles_malformed(self) -> None:
        assert _parse_verify_response("broken") == []

    def test_handles_empty(self) -> None:
        assert _parse_verify_response('{"results": []}') == []


class TestVerifyCandidatesWithLlm:
    def test_returns_original_without_api_key(self) -> None:
        suggestions = [LlmSuggestion(10.0, 50.0, "t", "r", 8.0)]
        segments = [_make_segment(10.0, 50.0, "text")]
        result = verify_candidates_with_llm(suggestions, segments)  # type: ignore[arg-type]
        assert len(result) == 1
        assert result[0].score == 8.0

    def test_returns_empty_for_empty_input(self) -> None:
        assert verify_candidates_with_llm([], []) == []


class TestBuildFewShotExamples:
    def test_returns_empty_without_db(self) -> None:
        assert _build_few_shot_examples(None) == ""

    def test_returns_empty_with_zero_count(self) -> None:
        assert _build_few_shot_examples(None, max_count=0) == ""


class TestSnapEndToSentenceBoundary:
    def test_snaps_to_last_subtitle_end(self) -> None:
        segments = [
            _make_segment(100.0, 130.0, "첫 대사"),
            _make_segment(130.0, 165.0, "두 번째 대사"),
            _make_segment(165.0, 168.0, "세 번째 대사가 진행 중..."),
        ]
        # 끝점 170 → 168.0(마지막 완결 자막)으로 당겨져야 함
        result = _snap_end_to_sentence_boundary(100.0, 170.0, segments)  # type: ignore[arg-type]
        assert result == 168.0

    def test_no_snap_if_too_far(self) -> None:
        segments = [_make_segment(100.0, 130.0, "대사")]
        # 끝점 170 — 마지막 자막 130.0은 40초 전이라 max_pull(8초) 초과
        result = _snap_end_to_sentence_boundary(100.0, 170.0, segments)  # type: ignore[arg-type]
        assert result == 170.0

    def test_no_snap_if_too_short(self) -> None:
        segments = [_make_segment(100.0, 110.0, "짧은 대사")]
        # 스냅하면 구간이 10초(< min_duration 25초)이므로 원본 유지
        result = _snap_end_to_sentence_boundary(100.0, 115.0, segments)  # type: ignore[arg-type]
        assert result == 115.0

    def test_empty_segments(self) -> None:
        result = _snap_end_to_sentence_boundary(100.0, 170.0, [])
        assert result == 170.0


class TestDetectForeignSceneGaps:
    def test_single_span_when_no_gap(self) -> None:
        segments = [
            _make_segment(10.0, 20.0, "대사1"),
            _make_segment(20.5, 30.0, "대사2"),
            _make_segment(30.5, 40.0, "대사3"),
        ]
        spans = _detect_foreign_scene_gaps(10.0, 40.0, segments, [])  # type: ignore[arg-type]
        assert len(spans) == 1
        assert spans[0]["role"] == "main"

    def test_splits_on_large_gap(self) -> None:
        segments = [
            _make_segment(10.0, 25.0, "A장면 대사"),
            # 25~45초: 20초 공백 (B장면 — 자막 없음)
            _make_segment(45.0, 60.0, "A장면 복귀 대사"),
        ]
        spans = _detect_foreign_scene_gaps(10.0, 60.0, segments, [])  # type: ignore[arg-type]
        assert len(spans) == 2
        assert spans[0]["end_time"] == 25.0
        assert spans[1]["start_time"] == 45.0

    def test_no_split_on_small_gap(self) -> None:
        segments = [
            _make_segment(10.0, 25.0, "대사1"),
            # 25~30초: 5초 공백 (threshold 8초 미만)
            _make_segment(30.0, 45.0, "대사2"),
        ]
        spans = _detect_foreign_scene_gaps(10.0, 45.0, segments, [])  # type: ignore[arg-type]
        assert len(spans) == 1

    def test_empty_segments_returns_single(self) -> None:
        spans = _detect_foreign_scene_gaps(10.0, 50.0, [], [])
        assert len(spans) == 1
        assert spans[0]["role"] == "main"


class TestScoredWindowComposite:
    def test_composite_metadata_when_gap(self) -> None:
        """중간 공백이 있으면 arc_form=composite, clip_spans가 분리됨."""
        suggestions = [
            LlmSuggestion(start_time=10.0, end_time=60.0, title="t", reason="r", score=8.0),
        ]
        segments = [
            _make_segment(10.0, 25.0, "A장면"),
            # 25~45초: 20초 공백
            _make_segment(45.0, 58.0, "A장면 복귀"),
        ]
        windows = llm_suggestions_to_scored_windows(suggestions, segments)  # type: ignore[arg-type]
        w = windows[0]
        assert w.metadata_json["arc_form"] == "composite"
        assert w.metadata_json["composite"] is True
        assert len(w.metadata_json["clip_spans"]) == 2

    def test_contiguous_metadata_when_no_gap(self) -> None:
        """공백 없으면 arc_form=contiguous, 단일 span."""
        suggestions = [
            LlmSuggestion(start_time=10.0, end_time=50.0, title="t", reason="r", score=7.0),
        ]
        segments = [
            _make_segment(10.0, 30.0, "대사1"),
            _make_segment(30.5, 48.0, "대사2"),
        ]
        windows = llm_suggestions_to_scored_windows(suggestions, segments)  # type: ignore[arg-type]
        w = windows[0]
        assert w.metadata_json["arc_form"] == "contiguous"
        assert w.metadata_json["composite"] is False
