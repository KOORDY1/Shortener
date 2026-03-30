from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SMOKE_DATA_DIR = BASE_DIR / "data" / "smoke"
SMOKE_STORAGE_DIR = BASE_DIR / "storage" / "smoke"


def prepare_smoke_env() -> None:
    if SMOKE_DATA_DIR.exists():
        shutil.rmtree(SMOKE_DATA_DIR, ignore_errors=True)
    if SMOKE_STORAGE_DIR.exists():
        shutil.rmtree(SMOKE_STORAGE_DIR, ignore_errors=True)

    SMOKE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    SMOKE_STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    os.environ["DATABASE_URL"] = f"sqlite:///{(SMOKE_DATA_DIR / 'smoke.db').as_posix()}"
    os.environ["STORAGE_ROOT"] = str(SMOKE_STORAGE_DIR)
    os.environ["CELERY_BROKER_URL"] = "memory://"
    os.environ["CELERY_RESULT_BACKEND"] = "cache+memory://"
    os.environ["CELERY_TASK_ALWAYS_EAGER"] = "true"
    os.environ["ALLOW_MOCK_LLM_FALLBACK"] = "true"
    os.environ["OPENAI_API_KEY"] = ""


def build_smoke_video_bytes() -> bytes:
    output_path = SMOKE_DATA_DIR / "sample.mp4"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=#202020:s=1280x720:d=18",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:sample_rate=44100:d=18",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path.read_bytes()


def run() -> None:
    prepare_smoke_env()
    video_bytes = build_smoke_video_bytes()

    from fastapi.testclient import TestClient

    from app.db.models import TranscriptSegment
    from app.services.candidate_events import CandidateEvent
    from app.services.candidate_generation import ScoredWindow, WindowSeed, dedupe_scored_windows, score_window
    from app.services.candidate_language_signals import extract_tokens, tone_signals
    from app.services.composite_candidate_generation import build_composite_candidates
    from app.main import create_app

    english_signals = tone_signals("What? No way, seriously, that's ridiculous. I am sorry, but I told you.")
    assert english_signals["comedy_signal"] > 0
    assert english_signals["emotion_signal"] > 0
    assert english_signals["reaction_signal"] > 0

    question_event = CandidateEvent(
        start_time=0.0,
        end_time=16.0,
        text="Why would you do that?",
        cue_count=2,
        shot_count=2,
        event_kind="question",
        tone_signals=tone_signals("Why would you do that?"),
        tokens=extract_tokens("Why would you do that?"),
        dominant_entities=["you"],
        source_segments=[],
    )
    answer_event = CandidateEvent(
        start_time=16.0,
        end_time=34.0,
        text="Because I told you already. Seriously, that is the whole point.",
        cue_count=3,
        shot_count=2,
        event_kind="payoff",
        tone_signals=tone_signals("Because I told you already. Seriously, that is the whole point."),
        tokens=extract_tokens("Because I told you already. Seriously, that is the whole point."),
        dominant_entities=["you"],
        source_segments=[],
    )
    structure_window = score_window(
        WindowSeed(
            start_time=0.0,
            end_time=34.0,
            events=[question_event, answer_event],
            window_reason="question_answer",
        ),
        segments=[
            TranscriptSegment(
                id="seg-1",
                episode_id="episode",
                segment_index=1,
                start_time=0.0,
                end_time=16.0,
                text="Why would you do that?",
                speaker_label=None,
            ),
            TranscriptSegment(
                id="seg-2",
                episode_id="episode",
                segment_index=2,
                start_time=16.0,
                end_time=34.0,
                text="Because I told you already. Seriously, that is the whole point.",
                speaker_label=None,
            ),
        ],
        shots=[],
    )
    assert structure_window is not None
    assert structure_window.metadata_json["question_answer_score"] > 0.4
    assert structure_window.metadata_json["payoff_end_weight"] > 0.2
    assert structure_window.metadata_json["ranking_focus"] in {"setup_payoff", "argument_turn", "reaction_turn"}

    short_punchy = ScoredWindow(
        start_time=0.0,
        end_time=32.0,
        total_score=9.4,
        scores_json={"total_score": 9.4},
        title_hint="short punchy",
        metadata_json={"transcript_excerpt": "short punchy", "dedupe_tokens": ["short", "punchy"]},
    )
    long_soft = ScoredWindow(
        start_time=40.0,
        end_time=120.0,
        total_score=8.1,
        scores_json={"total_score": 8.1},
        title_hint="long soft",
        metadata_json={"transcript_excerpt": "long soft", "dedupe_tokens": ["long", "soft"]},
    )
    deduped_order = dedupe_scored_windows([long_soft, short_punchy], limit=2)
    assert deduped_order[0].title_hint == "short punchy"

    app = create_app()
    with TestClient(app) as client:
        create_response = client.post(
            "/api/v1/episodes",
            data={
                "show_title": "Silicon Valley",
                "season_number": "1",
                "episode_number": "3",
                "episode_title": "Articles of Incorporation",
                "original_language": "en",
                "target_channel": "kr_us_drama",
            },
            files={"video_file": ("episode.mp4", video_bytes, "video/mp4")},
        )
        create_response.raise_for_status()
        episode = create_response.json()
        episode_id = episode["id"]

        analyze_response = client.post(
            f"/api/v1/episodes/{episode_id}/analyze",
            json={"force_reanalyze": False},
        )
        analyze_response.raise_for_status()
        analyze_job = analyze_response.json()

        job_response = client.get(f"/api/v1/jobs/{analyze_job['job_id']}")
        job_response.raise_for_status()
        job_payload = job_response.json()
        assert job_payload["status"] == "succeeded", job_payload

        episode_jobs = client.get(f"/api/v1/episodes/{episode_id}/jobs")
        episode_jobs.raise_for_status()
        assert episode_jobs.json()["total"] >= 1

        candidates_response = client.get(f"/api/v1/episodes/{episode_id}/candidates")
        candidates_response.raise_for_status()
        candidates = candidates_response.json()["items"]
        assert candidates, "Expected candidates to be generated"
        candidate_id = candidates[0]["id"]

        detail = client.get(f"/api/v1/candidates/{candidate_id}")
        detail.raise_for_status()
        assert "shots" in detail.json() and isinstance(detail.json()["shots"], list)

        drafts_response = client.post(
            f"/api/v1/candidates/{candidate_id}/script-drafts",
            json={
                "language": "ko",
                "versions": 2,
                "tone": "sharp_explanatory",
                "channel_style": "kr_us_drama",
                "force_regenerate": True,
            },
        )
        drafts_response.raise_for_status()
        draft_job = drafts_response.json()

        draft_job_response = client.get(f"/api/v1/jobs/{draft_job['job_id']}")
        draft_job_response.raise_for_status()
        draft_job_payload = draft_job_response.json()
        assert draft_job_payload["status"] == "succeeded", draft_job_payload

        final_drafts_response = client.get(f"/api/v1/candidates/{candidate_id}/script-drafts")
        final_drafts_response.raise_for_status()
        script_drafts = final_drafts_response.json()["items"]
        assert len(script_drafts) == 2, script_drafts
        script_draft_id = script_drafts[0]["id"]

        vd_create = client.post(
            f"/api/v1/candidates/{candidate_id}/video-drafts",
            json={
                "script_draft_id": script_draft_id,
                "template_type": "dramashorts_v1",
                "render_config": {
                    "intro_tts_enabled": True,
                    "intro_tts_text": "인트로 테스트 문장입니다.",
                    "intro_duration_sec": 1.8,
                    "outro_tts_enabled": True,
                    "outro_tts_text": "아웃트로 테스트 문장입니다.",
                    "outro_duration_sec": 1.6
                },
            },
        )
        vd_create.raise_for_status()
        video_draft_id = vd_create.json()["video_draft_id"]
        assert vd_create.json()["job_id"]
        assert video_draft_id

        vd_get = client.get(f"/api/v1/video-drafts/{video_draft_id}")
        vd_get.raise_for_status()
        draft_body = vd_get.json()
        assert draft_body["status"] == "ready"
        tts_segments = draft_body["metadata"].get("tts_segments") or []
        assert len(tts_segments) >= 2, draft_body["metadata"]
        assert all(segment["final_segment_duration_sec"] > 0 for segment in tts_segments)
        assert any(segment["provider"] == "silent_fallback" for segment in tts_segments)

        patch_resp = client.patch(
            f"/api/v1/video-drafts/{video_draft_id}",
            json={
                "render_config": {
                    **draft_body["render_config"],
                    "text_slots": {
                        **draft_body["render_config"].get("text_slots", {}),
                        "top_title": {
                            **draft_body["render_config"].get("text_slots", {}).get("top_title", {}),
                            "text": "패치된 훅 문구"
                        }
                    }
                }
            },
        )
        patch_resp.raise_for_status()

        rerender = client.post(f"/api/v1/video-drafts/{video_draft_id}/rerender", json={})
        rerender.raise_for_status()
        rerender_payload = rerender.json()
        assert rerender_payload.get("job_id")

        approve = client.post(f"/api/v1/video-drafts/{video_draft_id}/approve", json={})
        approve.raise_for_status()
        assert approve.json()["status"] == "approved"

        export_resp = client.post(
            f"/api/v1/video-drafts/{video_draft_id}/exports",
            json={
                "export_preset": "review_lowres",
                "include_srt": True,
                "include_script_txt": True,
                "include_metadata_json": True,
            },
        )
        export_resp.raise_for_status()
        export_id = export_resp.json()["export_id"]
        assert export_resp.json()["job_id"]
        assert export_id

        export_get = client.get(f"/api/v1/exports/{export_id}")
        export_get.raise_for_status()
        export_body = export_get.json()
        assert export_body["status"] == "ready"
        assert export_body.get("export_video_path")
        assert export_body["export_preset"] == "review_lowres"
        assert export_body["metadata"].get("preset_profile")

        composite_candidates = build_composite_candidates(
            [
                ScoredWindow(
                    start_time=10.0,
                    end_time=42.0,
                    total_score=8.9,
                    scores_json={"total_score": 8.9},
                    title_hint="setup",
                    metadata_json={
                        "dedupe_tokens": ["리처드", "투자", "제안"],
                        "dominant_entities": ["리처드", "투자"],
                        "ranking_focus": "comedy_or_emotion",
                        "transcript_excerpt": "리처드가 투자 제안을 듣는다",
                        "source_events": [
                            {
                                "start_time": 10.0,
                                "end_time": 24.0,
                                "event_kind": "question",
                                "text": "투자를 받을 생각이 있나?",
                                "tone_signals": {"question_signal": 0.9},
                                "dominant_entities": ["리처드", "투자"],
                                "setup_score": 0.7,
                                "payoff_score": 0.1,
                                "standalone_score": 0.5,
                                "context_dependency_score": 0.1,
                            }
                        ],
                        "question_answer_score": 0.8,
                    },
                ),
                ScoredWindow(
                    start_time=58.0,
                    end_time=88.0,
                    total_score=8.7,
                    scores_json={"total_score": 8.7},
                    title_hint="payoff",
                    metadata_json={
                        "dedupe_tokens": ["리처드", "투자", "거절"],
                        "dominant_entities": ["리처드", "투자"],
                        "ranking_focus": "comedy_or_emotion",
                        "transcript_excerpt": "리처드가 투자 제안을 거절한다",
                        "source_events": [
                            {
                                "start_time": 58.0,
                                "end_time": 72.0,
                                "event_kind": "reaction",
                                "text": "정말 그 제안을 거절한다고?",
                                "tone_signals": {"reaction_signal": 0.8},
                                "dominant_entities": ["리처드", "투자"],
                                "setup_score": 0.1,
                                "payoff_score": 0.7,
                                "reaction_score": 0.6,
                                "standalone_score": 0.4,
                                "context_dependency_score": 0.2,
                            }
                        ],
                        "payoff_end_weight": 0.7,
                        "reaction_shift_score": 0.65,
                    },
                ),
            ]
        )
        assert composite_candidates, "Expected composite heuristic to produce at least one pair"
        first_comp = composite_candidates[0]
        assert first_comp.metadata_json.get("arc_reason") or first_comp.metadata_json.get("pair_reason"), \
            "Composite must have arc_reason or pair_reason"

        # ===== narrative arc regression tests =====
        _test_narrative_arc_regression()

        print(
            json.dumps(
                {
                    "episode_id": episode_id,
                    "analysis_job_id": analyze_job["job_id"],
                    "candidate_id": candidate_id,
                    "script_job_id": draft_job["job_id"],
                    "script_draft_ids": [item["id"] for item in script_drafts],
                    "video_draft_id": video_draft_id,
                    "rerender_job_id": rerender_payload["job_id"],
                    "export_id": export_id,
                },
                indent=2,
            )
        )


def _test_narrative_arc_regression() -> None:
    """narrative arc 파이프라인의 핵심 동작을 검증하는 unit-ish regression checks."""
    from app.services.candidate_events import CandidateEvent
    from app.services.candidate_generation import ScoredWindow
    from app.services.candidate_language_signals import extract_tokens, tone_signals
    from app.services.candidate_role_scoring import compute_role_scores
    from app.services.candidate_arc_search import beam_search_arcs
    from app.services.candidate_spans import pad_spans_to_minimum, extract_core_support_summary
    from app.services.candidate_rerank import rerank_scored_windows

    # -- Test 1: contiguous single arc (setup→payoff 충분) 우선순위 --
    contiguous_window = ScoredWindow(
        start_time=0.0, end_time=45.0, total_score=8.0,
        scores_json={"total_score": 8.0},
        title_hint="contiguous arc",
        metadata_json={
            "arc_form": "contiguous",
            "single_arc_complete_score": 0.6,
            "source_events": [
                {"start_time": 0.0, "end_time": 15.0, "setup_score": 0.7, "payoff_score": 0.1,
                 "standalone_score": 0.5, "context_dependency_score": 0.1, "event_kind": "question"},
                {"start_time": 30.0, "end_time": 45.0, "setup_score": 0.1, "payoff_score": 0.8,
                 "standalone_score": 0.5, "context_dependency_score": 0.1, "event_kind": "payoff"},
            ],
            "entity_consistency": 0.5,
            "standalone_clarity": 0.6,
            "window_duration_sec": 45.0,
        },
    )
    composite_window = ScoredWindow(
        start_time=0.0, end_time=90.0, total_score=8.0,
        scores_json={"total_score": 8.0},
        title_hint="composite arc",
        metadata_json={
            "arc_form": "composite",
            "composite": True,
            "source_events": [
                {"start_time": 0.0, "end_time": 15.0, "setup_score": 0.5, "payoff_score": 0.1,
                 "standalone_score": 0.4, "context_dependency_score": 0.2, "event_kind": "dialogue"},
                {"start_time": 60.0, "end_time": 90.0, "setup_score": 0.1, "payoff_score": 0.5,
                 "standalone_score": 0.4, "context_dependency_score": 0.3, "event_kind": "reaction"},
            ],
            "entity_consistency": 0.3,
            "standalone_clarity": 0.4,
            "window_duration_sec": 90.0,
        },
    )
    reranked = rerank_scored_windows([contiguous_window, composite_window])
    assert reranked[0].metadata_json["arc_form"] == "contiguous", \
        "Test 1 FAIL: contiguous complete arc should rank above comparable composite"

    # -- Test 2: 2~4 event beam search가 pair보다 자연스러운 arc 선택 --
    events_for_beam = [
        CandidateEvent(
            start_time=0.0, end_time=12.0, text="Why would you invest in this?",
            cue_count=2, shot_count=1, event_kind="question",
            tone_signals=tone_signals("Why would you invest in this?"),
            tokens=extract_tokens("Why would you invest in this?"),
            dominant_entities=["invest"], source_segments=[],
            setup_score=0.7, escalation_score=0.1, reaction_score=0.1, payoff_score=0.05,
            standalone_score=0.5, context_dependency_score=0.1,
            visual_impact_score=0.0, audio_impact_score=0.0,
        ),
        CandidateEvent(
            start_time=12.0, end_time=22.0, text="Because the market is completely insane right now.",
            cue_count=2, shot_count=1, event_kind="tension",
            tone_signals=tone_signals("Because the market is completely insane right now."),
            tokens=extract_tokens("Because the market is completely insane right now."),
            dominant_entities=["market"], source_segments=[],
            setup_score=0.1, escalation_score=0.5, reaction_score=0.2, payoff_score=0.1,
            standalone_score=0.4, context_dependency_score=0.2,
            visual_impact_score=0.0, audio_impact_score=0.0,
        ),
        CandidateEvent(
            start_time=22.0, end_time=35.0, text="No way. That is the whole point! Told you!",
            cue_count=3, shot_count=2, event_kind="payoff",
            tone_signals=tone_signals("No way. That is the whole point! Told you!"),
            tokens=extract_tokens("No way. That is the whole point! Told you!"),
            dominant_entities=["invest"], source_segments=[],
            setup_score=0.05, escalation_score=0.1, reaction_score=0.4, payoff_score=0.7,
            standalone_score=0.5, context_dependency_score=0.1,
            visual_impact_score=0.0, audio_impact_score=0.0,
        ),
    ]
    arcs = beam_search_arcs(events_for_beam)
    assert len(arcs) >= 1, "Test 2 FAIL: beam search should find at least one arc"
    best_arc = arcs[0]
    assert len(best_arc.events) >= 2, "Test 2 FAIL: arc should have at least 2 events"
    assert best_arc.events[-1].payoff_score >= 0.3, \
        "Test 2 FAIL: last event in arc should have reasonable payoff_score"

    # -- Test 3: core span 20초 + support padding = 30초 이상 --
    short_core_spans = [
        {"start_time": 10.0, "end_time": 30.0, "order": 0, "role": "main"},
    ]
    padded, support_added = pad_spans_to_minimum(
        short_core_spans, timeline_start=0.0, timeline_end=120.0, min_duration=30.0,
    )
    total_dur = sum(s["end_time"] - s["start_time"] for s in padded)
    assert total_dur >= 30.0, \
        f"Test 3 FAIL: padded duration {total_dur:.1f}s should be >= 30s"
    assert support_added > 0, "Test 3 FAIL: support should have been added"
    summary = extract_core_support_summary(padded)
    assert summary["core_duration_sec"] > 0, "Test 3 FAIL: core_duration_sec should be > 0"

    # -- Test 4: 대사 적지만 visual/audio impact 강한 후보가 탈락하지 않음 --
    visual_candidate = ScoredWindow(
        start_time=0.0, end_time=40.0, total_score=5.5,
        scores_json={"total_score": 5.5, "visual_impact": 0.7, "audio_impact": 0.5},
        title_hint="visual impact scene",
        metadata_json={
            "candidate_track": "visual",
            "arc_form": "contiguous",
            "speech_coverage": 0.05,
            "visual_impact": 0.7,
            "audio_impact": 0.5,
            "standalone_clarity": 0.3,
            "source_events": [],
            "window_duration_sec": 40.0,
        },
    )
    dialogue_candidate = ScoredWindow(
        start_time=50.0, end_time=90.0, total_score=6.0,
        scores_json={"total_score": 6.0},
        title_hint="dialogue heavy",
        metadata_json={
            "candidate_track": "dialogue",
            "arc_form": "contiguous",
            "speech_coverage": 0.8,
            "source_events": [],
            "window_duration_sec": 40.0,
        },
    )
    reranked_va = rerank_scored_windows([visual_candidate, dialogue_candidate])
    visual_found = any(w.metadata_json.get("candidate_track") == "visual" for w in reranked_va)
    assert visual_found, "Test 4 FAIL: visual impact candidate should not be completely dropped"

    # -- Test 5: payoff_strength 약한 arc는 높은 순위 못 받음 --
    strong_payoff = ScoredWindow(
        start_time=0.0, end_time=45.0, total_score=7.0,
        scores_json={"total_score": 7.0},
        title_hint="strong payoff",
        metadata_json={
            "arc_form": "contiguous",
            "source_events": [
                {"start_time": 0.0, "end_time": 15.0, "setup_score": 0.5, "payoff_score": 0.1,
                 "standalone_score": 0.5, "context_dependency_score": 0.1, "event_kind": "question"},
                {"start_time": 30.0, "end_time": 45.0, "setup_score": 0.1, "payoff_score": 0.8,
                 "standalone_score": 0.5, "context_dependency_score": 0.1, "event_kind": "payoff"},
            ],
            "entity_consistency": 0.5,
            "standalone_clarity": 0.6,
            "window_duration_sec": 45.0,
        },
    )
    weak_payoff = ScoredWindow(
        start_time=50.0, end_time=95.0, total_score=7.5,
        scores_json={"total_score": 7.5},
        title_hint="weak payoff",
        metadata_json={
            "arc_form": "contiguous",
            "source_events": [
                {"start_time": 50.0, "end_time": 65.0, "setup_score": 0.6, "payoff_score": 0.05,
                 "standalone_score": 0.5, "context_dependency_score": 0.1, "event_kind": "question"},
                {"start_time": 80.0, "end_time": 95.0, "setup_score": 0.1, "payoff_score": 0.05,
                 "standalone_score": 0.4, "context_dependency_score": 0.2, "event_kind": "dialogue"},
            ],
            "entity_consistency": 0.3,
            "standalone_clarity": 0.4,
            "window_duration_sec": 45.0,
        },
    )
    reranked_payoff = rerank_scored_windows([weak_payoff, strong_payoff])
    assert reranked_payoff[0].title_hint == "strong payoff", \
        "Test 5 FAIL: strong payoff arc should rank above weak payoff even with lower initial score"

    # -- Test 6: composite metadata에 arc_reason, core/support, payoff_anchor 존재 --
    from app.services.candidate_arc_search import ArcCandidate, arc_to_scored_window_metadata
    test_arc = ArcCandidate(
        events=events_for_beam,
        arc_scores={
            "total_arc_score": 0.6,
            "arc_setup_strength": 0.7,
            "arc_payoff_strength": 0.7,
            "arc_continuity_score": 0.3,
            "arc_standalone_score": 0.5,
            "arc_visual_audio_bonus": 0.0,
            "arc_context_penalty": 0.0,
            "arc_escalation_strength": 0.3,
            "setup_to_payoff_delta": 0.4,
        },
        arc_form="contiguous",
        arc_reason="setup(question)_to_payoff(payoff)",
    )
    arc_meta = arc_to_scored_window_metadata(test_arc)
    assert "arc_reason" in arc_meta, "Test 6 FAIL: arc metadata should have arc_reason"
    assert "payoff_anchor" in arc_meta, "Test 6 FAIL: arc metadata should have payoff_anchor"
    assert "core_spans" in arc_meta, "Test 6 FAIL: arc metadata should have core_spans"
    assert "support_spans" in arc_meta, "Test 6 FAIL: arc metadata should have support_spans"
    assert arc_meta["payoff_anchor"]["payoff_score"] > 0, \
        "Test 6 FAIL: payoff_anchor should have positive payoff_score"
    assert "support_added_sec" in arc_meta, "Test 6 FAIL: arc metadata should have support_added_sec"

    print("  [OK] All 6 narrative arc regression tests passed.")

    # ===== episode-boundary & entity regression tests =====
    _test_episode_boundary_and_entity_regression()


def _test_episode_boundary_and_entity_regression() -> None:
    """episode boundary padding + frequency-aware entity regression checks."""
    from app.services.candidate_spans import pad_spans_to_minimum
    from app.services.candidate_language_signals import (
        extract_tokens,
        extract_token_stream,
        dominant_entities,
    )
    from app.services.candidate_arc_search import ArcCandidate, arc_to_scored_window_metadata
    from app.services.candidate_events import CandidateEvent
    from app.services.candidate_language_signals import tone_signals
    from app.services.candidate_rerank import rerank_scored_windows
    from app.services.candidate_generation import ScoredWindow

    # -- Test 7: support padding이 episode boundary 밖으로 안 나감 --
    episode_end = 60.0
    core_spans = [{"start_time": 50.0, "end_time": 58.0, "order": 0, "role": "main"}]
    padded, added = pad_spans_to_minimum(
        core_spans, timeline_start=0.0, timeline_end=episode_end, min_duration=30.0,
    )
    for span in padded:
        assert span["end_time"] <= episode_end, \
            f"Test 7 FAIL: span end {span['end_time']} exceeds episode end {episode_end}"
        assert span["start_time"] >= 0.0, \
            f"Test 7 FAIL: span start {span['start_time']} is before timeline start"
    print("  [OK] Test 7: support padding stays within episode boundary")

    # -- Test 8: contiguous 후보 padding도 실제 timeline_end 안에서만 생김 --
    near_end_spans = [{"start_time": 55.0, "end_time": 59.0, "order": 0, "role": "main"}]
    padded2, _ = pad_spans_to_minimum(
        near_end_spans, timeline_start=0.0, timeline_end=episode_end, min_duration=30.0,
    )
    for span in padded2:
        assert span["end_time"] <= episode_end, \
            f"Test 8 FAIL: contiguous padding exceeds timeline_end"
    print("  [OK] Test 8: contiguous padding respects timeline_end")

    # -- Test 9: raw frequency token 기반 entity가 dedupe token보다 강한 케이스 --
    text = "Richard Richard Richard likes investing. Investing is key for Richard."
    dedupe_tokens = extract_tokens(text)
    raw_stream = extract_token_stream(text)
    entities_from_dedupe = dominant_entities(dedupe_tokens, limit=3)
    entities_from_raw = dominant_entities(raw_stream, limit=3)
    assert len(raw_stream) > len(dedupe_tokens), \
        "Test 9 FAIL: raw stream should have more tokens than dedupe"
    assert entities_from_raw[0] == "richard" if "richard" in [t.lower() for t in raw_stream] else True, \
        "Test 9 FAIL: frequency-based entity should rank repeated tokens higher"
    print(f"  [OK] Test 9: raw stream={len(raw_stream)} > dedupe={len(dedupe_tokens)}, top entity={entities_from_raw[0] if entities_from_raw else 'none'}")

    # -- Test 10: stronger entity continuity가 있는 arc가 유리 --
    strong_entity_window = ScoredWindow(
        start_time=0.0, end_time=45.0, total_score=7.0,
        scores_json={"total_score": 7.0},
        title_hint="strong entity",
        metadata_json={
            "arc_form": "composite",
            "composite": True,
            "arc_continuity_score": 0.7,
            "source_events": [
                {"start_time": 0.0, "end_time": 15.0, "setup_score": 0.5, "payoff_score": 0.1,
                 "standalone_score": 0.5, "context_dependency_score": 0.1, "event_kind": "question"},
                {"start_time": 30.0, "end_time": 45.0, "setup_score": 0.1, "payoff_score": 0.6,
                 "standalone_score": 0.5, "context_dependency_score": 0.1, "event_kind": "payoff"},
            ],
            "entity_consistency": 0.7,
            "standalone_clarity": 0.5,
            "window_duration_sec": 45.0,
        },
    )
    weak_entity_window = ScoredWindow(
        start_time=50.0, end_time=95.0, total_score=7.0,
        scores_json={"total_score": 7.0},
        title_hint="weak entity",
        metadata_json={
            "arc_form": "composite",
            "composite": True,
            "arc_continuity_score": 0.05,
            "source_events": [
                {"start_time": 50.0, "end_time": 65.0, "setup_score": 0.5, "payoff_score": 0.1,
                 "standalone_score": 0.4, "context_dependency_score": 0.2, "event_kind": "question"},
                {"start_time": 80.0, "end_time": 95.0, "setup_score": 0.1, "payoff_score": 0.6,
                 "standalone_score": 0.4, "context_dependency_score": 0.2, "event_kind": "payoff"},
            ],
            "entity_consistency": 0.05,
            "standalone_clarity": 0.4,
            "window_duration_sec": 45.0,
        },
    )
    reranked = rerank_scored_windows([weak_entity_window, strong_entity_window])
    assert reranked[0].title_hint == "strong entity", \
        f"Test 10 FAIL: strong entity continuity should rank higher, got {reranked[0].title_hint}"
    print("  [OK] Test 10: stronger entity continuity composite ranks higher")

    print("  [OK] All 4 episode-boundary & entity regression tests passed.")

    _test_pair_fallback_regression()


def _test_pair_fallback_regression() -> None:
    """pair fallback composite가 설계 원칙(30초, core/support, episode-aware, arc-style metadata)을 따르는지 검증."""
    from app.services.candidate_generation import ScoredWindow
    from app.services.composite_candidate_generation import build_composite_candidates
    from app.services.candidate_spans import MIN_CANDIDATE_DURATION_SEC

    timeline_end = 120.0
    left_window = ScoredWindow(
        start_time=10.0, end_time=22.0, total_score=7.5,
        scores_json={"total_score": 7.5},
        title_hint="setup question",
        metadata_json={
            "dedupe_tokens": ["richard", "invest", "proposal"],
            "dominant_entities": ["richard", "invest"],
            "ranking_focus": "setup_payoff",
            "transcript_excerpt": "Are you going to invest?",
            "source_events": [
                {
                    "start_time": 10.0, "end_time": 22.0,
                    "event_kind": "question", "text": "Are you going to invest?",
                    "tone_signals": {"question_signal": 0.8},
                    "dominant_entities": ["richard", "invest"],
                    "setup_score": 0.7, "payoff_score": 0.05,
                    "standalone_score": 0.5, "context_dependency_score": 0.1,
                }
            ],
            "question_answer_score": 0.7,
        },
    )
    right_window = ScoredWindow(
        start_time=40.0, end_time=55.0, total_score=7.0,
        scores_json={"total_score": 7.0},
        title_hint="payoff reaction",
        metadata_json={
            "dedupe_tokens": ["richard", "invest", "reject"],
            "dominant_entities": ["richard", "invest"],
            "ranking_focus": "setup_payoff",
            "transcript_excerpt": "No way, that is insane!",
            "source_events": [
                {
                    "start_time": 40.0, "end_time": 55.0,
                    "event_kind": "reaction", "text": "No way, that is insane!",
                    "tone_signals": {"reaction_signal": 0.7, "payoff_signal": 0.5},
                    "dominant_entities": ["richard", "invest"],
                    "setup_score": 0.05, "payoff_score": 0.6,
                    "standalone_score": 0.5, "context_dependency_score": 0.15,
                }
            ],
            "payoff_end_weight": 0.6,
            "reaction_shift_score": 0.5,
        },
    )

    composites = build_composite_candidates(
        [left_window, right_window], timeline_end=timeline_end,
    )

    pair_composites = [
        c for c in composites
        if c.metadata_json.get("generated_by", "").startswith("composite_pair")
    ]

    if not pair_composites:
        print("  [SKIP] No pair fallback composites generated (beam search may have covered)")
        print("  [OK] All 4 pair fallback regression tests skipped (no pair fallback produced)")
        return

    pc = pair_composites[0]
    meta = pc.metadata_json

    # Test 11: pair fallback은 최종 30초 이상
    clip_spans = meta.get("clip_spans", [])
    total_dur = sum(s["end_time"] - s["start_time"] for s in clip_spans)
    assert total_dur >= MIN_CANDIDATE_DURATION_SEC, \
        f"Test 11 FAIL: pair fallback total duration {total_dur:.1f}s < {MIN_CANDIDATE_DURATION_SEC}s"
    print(f"  [OK] Test 11: pair fallback total duration {total_dur:.1f}s >= {MIN_CANDIDATE_DURATION_SEC}s")

    # Test 12: pair fallback에 core_spans, support_spans, support_added_sec 존재
    assert "core_spans" in meta, "Test 12 FAIL: missing core_spans"
    assert "support_spans" in meta, "Test 12 FAIL: missing support_spans"
    assert "support_added_sec" in meta, "Test 12 FAIL: missing support_added_sec"
    print("  [OK] Test 12: pair fallback has core_spans, support_spans, support_added_sec")

    # Test 13: pair fallback span이 timeline_end를 넘지 않음
    for span in clip_spans:
        assert span["end_time"] <= timeline_end, \
            f"Test 13 FAIL: span end {span['end_time']} > timeline_end {timeline_end}"
        assert span["start_time"] >= 0.0, \
            f"Test 13 FAIL: span start {span['start_time']} < 0"
    print("  [OK] Test 13: pair fallback spans within episode boundary")

    # Test 14: pair fallback에 arc_reason, payoff_anchor, arc_form 존재
    assert "arc_reason" in meta, "Test 14 FAIL: missing arc_reason"
    assert "payoff_anchor" in meta, "Test 14 FAIL: missing payoff_anchor"
    assert meta.get("arc_form") == "composite", "Test 14 FAIL: arc_form should be 'composite'"
    assert "arc_continuity_score" in meta, "Test 14 FAIL: missing arc_continuity_score"
    print("  [OK] Test 14: pair fallback has arc-style metadata")

    print("  [OK] All 4 pair fallback regression tests passed.")


if __name__ == "__main__":
    run()
