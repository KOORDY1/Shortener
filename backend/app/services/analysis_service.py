from __future__ import annotations

import logging
import time
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    Candidate,
    CandidateStatus,
    Episode,
    EpisodeStatus,
    Shot,
    TranscriptSegment,
)
from app.services.analysis_metadata import mark_analysis_completed, mark_analysis_running
from app.services.candidate_spans import candidate_clip_spans, clip_spans_total_duration
from app.services.candidate_rerank import rerank_candidates_for_episode
from app.services.storage_service import episode_root, write_placeholder
from app.services.candidate_generation import ScoredWindow, build_candidates_for_episode, dedupe_scored_windows
from app.services.composite_candidate_generation import build_composite_candidates
from app.services.keyframe_extraction import extract_keyframes_for_episode
from app.services.media_probe import probe_media_metadata
from app.services.proxy_transcoding import ensure_analysis_proxy
from app.services.shot_detection import (
    deserialize_shot_intervals,
    detect_shot_intervals_for_episode,
    extract_shot_thumbnail,
    serialize_shot_intervals,
    shot_detection_cache_key,
)
from app.services.subtitle_parse import parse_subtitle_upload_file
from app.services.vision_candidate_refinement import refine_candidates_with_vision

logger = logging.getLogger(__name__)


def _episode_media_path(path_str: str | None) -> Path | None:
    if not path_str:
        return None
    raw = Path(path_str).expanduser()
    path = (
        raw.resolve()
        if raw.is_absolute()
        else (get_settings().resolved_storage_root / raw).resolve()
    )
    return path if path.is_file() else None


def ingest_episode_step(db: Session, episode_id: str) -> dict:
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise ValueError("Episode not found")
    if not Path(episode.source_video_path).exists():
        raise FileNotFoundError("Source video file is missing")

    probe_summary = probe_media_metadata(Path(episode.source_video_path))
    probe_ok = probe_summary.get("status") == "ok"
    episode.status = EpisodeStatus.PROCESSING.value
    episode.duration_seconds = float(probe_summary["duration_seconds"] or episode.duration_seconds or 42.0)
    episode.fps = float(probe_summary["fps"] or episode.fps or 23.976)
    episode.width = int(probe_summary["width"] or episode.width or 1920)
    episode.height = int(probe_summary["height"] or episode.height or 1080)

    metadata = dict(episode.metadata_json or {})
    metadata["ingest_mode"] = "ffprobe" if probe_ok else "fallback"
    metadata["source_verified"] = True
    metadata["media_probe"] = {
        "status": probe_summary.get("status"),
        "error": probe_summary.get("error"),
        "duration_seconds": probe_summary.get("duration_seconds"),
        "fps": probe_summary.get("fps"),
        "width": probe_summary.get("width"),
        "height": probe_summary.get("height"),
        "video_stream_found": probe_summary.get("video_stream_found"),
    }
    episode.metadata_json = metadata
    mark_analysis_running(episode, "ingest_episode")
    mark_analysis_completed(
        episode,
        "ingest_episode",
        step_details={
            "mode": metadata["ingest_mode"],
            "source_verified": True,
            "media_probe_status": probe_summary.get("status"),
            "video_stream_found": probe_summary.get("video_stream_found"),
            "fallback_used": not probe_ok,
        },
    )
    db.add(episode)
    db.commit()

    return {"episode_id": episode.id}


def transcode_proxy_step(db: Session, payload: dict) -> dict:
    episode = db.get(Episode, payload["episode_id"])
    if episode is None:
        raise ValueError("Episode not found")

    summary = ensure_analysis_proxy(episode, ignore_cache=bool(payload.get("ignore_cache")))
    meta = dict(episode.metadata_json or {})
    meta["proxy_transcode"] = summary
    episode.metadata_json = meta
    mark_analysis_running(episode, "transcode_proxy")
    mark_analysis_completed(
        episode,
        "transcode_proxy",
        step_details={
            "mode": summary.get("mode"),
            "status": summary.get("status"),
            "version": summary.get("version"),
        },
    )
    db.add(episode)
    db.commit()
    return payload


def detect_shots_step(db: Session, payload: dict) -> dict:
    """FFmpeg scene 필터로 컷 검출 후 샷 구간·썸네일 생성. 실패 시 길이 기준 균등 분할."""
    episode_id = payload["episode_id"]
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise ValueError("Episode not found")
    ignore_cache = bool(payload.get("ignore_cache"))

    existing_shots = list(
        db.scalars(
            select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.shot_index.asc())
        )
    )
    meta = dict(episode.metadata_json or {})
    shot_meta = dict(meta.get("shot_detection") or {})
    cache_key, video_path, source_kind = shot_detection_cache_key(episode)
    cached_intervals = deserialize_shot_intervals(shot_meta.get("intervals"))
    if not ignore_cache and (shot_meta.get("cache_key") == cache_key and len(cached_intervals) > 0):
        if len(existing_shots) != len(cached_intervals):
            db.execute(delete(Shot).where(Shot.episode_id == episode_id))
            for index, (start_time, end_time) in enumerate(cached_intervals, start=1):
                thumb_path = episode_root(episode_id) / "shots" / f"{index:04d}.jpg"
                thumbnail_path = str(thumb_path.resolve()) if thumb_path.is_file() else None
                db.add(
                    Shot(
                        episode_id=episode_id,
                        shot_index=index,
                        start_time=start_time,
                        end_time=end_time,
                        thumbnail_path=thumbnail_path,
                    )
                )
            db.flush()
            existing_shots = list(
                db.scalars(
                    select(Shot)
                    .where(Shot.episode_id == episode_id)
                    .order_by(Shot.shot_index.asc())
                )
            )
        if len(existing_shots) == len(cached_intervals) and len(existing_shots) > 0:
            shot_meta["status"] = "cached"
            shot_meta["shot_count"] = len(existing_shots)
            shot_meta["video_source"] = source_kind
            meta["shot_detection"] = shot_meta
            episode.metadata_json = meta
            mark_analysis_running(episode, "detect_shots")
            mark_analysis_completed(
                episode,
                "detect_shots",
                step_details={
                    "mode": shot_meta.get("mode"),
                    "shot_count": len(existing_shots),
                    "video_source": source_kind,
                    "status": "cached",
                },
            )
            db.add(episode)
            db.commit()
            return {**payload, "shot_detection_status": "cached"}

    db.execute(delete(Shot).where(Shot.episode_id == episode_id))
    intervals, det_mode, source_kind = detect_shot_intervals_for_episode(episode)
    video_ok = video_path.is_file() and video_path.stat().st_size >= 2048

    for index, (start_time, end_time) in enumerate(intervals, start=1):
        out_jpg = episode_root(episode_id) / "shots" / f"{index:04d}.jpg"
        if video_ok and extract_shot_thumbnail(video_path, start_time, out_jpg):
            thumbnail_path = str(out_jpg.resolve())
        else:
            thumbnail_path = write_placeholder(
                episode_id,
                ["shots", f"{index:04d}.jpg"],
                f"shot {index} (thumbnail fallback)",
            )
        db.add(
            Shot(
                episode_id=episode_id,
                shot_index=index,
                start_time=start_time,
                end_time=end_time,
                thumbnail_path=thumbnail_path,
            )
        )

    meta["shot_detection"] = {
        "mode": det_mode,
        "status": "completed",
        "shot_count": len(intervals),
        "video_source": source_kind,
        "cache_key": cache_key,
        "intervals": serialize_shot_intervals(intervals),
    }
    episode.metadata_json = meta
    mark_analysis_running(episode, "detect_shots")
    mark_analysis_completed(
        episode,
        "detect_shots",
        step_details={"mode": det_mode, "shot_count": len(intervals), "video_source": source_kind},
    )
    db.add(episode)
    db.commit()
    return payload


def extract_keyframes_step(db: Session, payload: dict) -> dict:
    episode_id = payload["episode_id"]
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise ValueError("Episode not found")

    shots = list(
        db.scalars(
            select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.shot_index.asc())
        )
    )
    mark_analysis_running(episode, "extract_keyframes")
    summary = extract_keyframes_for_episode(
        episode,
        shots,
        ignore_cache=bool(payload.get("ignore_cache")),
    )

    meta = dict(episode.metadata_json or {})
    meta["vision_scan"] = summary
    episode.metadata_json = meta
    mark_analysis_completed(
        episode,
        "extract_keyframes",
        step_details={
            "status": summary.get("status"),
            "frame_count": summary.get("frame_count", 0),
            "shots_with_keyframes": summary.get("shots_with_keyframes", 0),
            "version": summary.get("version"),
        },
    )
    db.add(episode)
    db.commit()
    return {
        **payload,
        "vision_scan_status": summary.get("status"),
        "vision_scan_frame_count": summary.get("frame_count", 0),
    }


def _save_transcript_cues(
    db: Session,
    episode_id: str,
    cues: list[tuple[float, float, str]],
) -> int:
    """(start, end, text) 튜플 목록을 TranscriptSegment로 저장하고 저장 개수를 반환한다."""
    count = 0
    for index, (start_time, end_time, text) in enumerate(cues, start=1):
        db.add(
            TranscriptSegment(
                episode_id=episode_id,
                segment_index=index,
                start_time=float(start_time),
                end_time=float(end_time),
                text=text,
                speaker_label=None,
            )
        )
        count = index
    return count


def extract_or_generate_transcript_step(db: Session, payload: dict) -> dict:
    """업로드 자막(SRT/WebVTT)을 파싱하거나, asr_enabled=True면 Whisper로 전사한다."""
    episode_id = payload["episode_id"]
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise ValueError("Episode not found")

    db.execute(delete(TranscriptSegment).where(TranscriptSegment.episode_id == episode_id))

    settings = get_settings()
    meta = dict(episode.metadata_json or {})
    sub_path = _episode_media_path(episode.source_subtitle_path)
    count = 0

    if sub_path is not None and sub_path.suffix.lower() in (".srt", ".vtt"):
        # 1순위: 업로드된 자막 파일
        try:
            cues = parse_subtitle_upload_file(sub_path)
            count = _save_transcript_cues(db, episode_id, cues)
            meta["transcript_source"] = "uploaded_subtitle"
            meta.pop("transcript_error", None)
        except OSError as exc:
            meta["transcript_source"] = "parse_failed"
            meta["transcript_error"] = str(exc)[:500]
    elif settings.asr_enabled:
        # 2순위: Whisper ASR (asr_enabled=True 일 때만)
        from app.services.asr_service import transcribe_audio

        meta_proxy = dict(episode.metadata_json or {})
        proxy_info = meta_proxy.get("proxy_transcode") or {}
        audio_path_str: str | None = proxy_info.get("audio_path") or proxy_info.get("audio_output_path")
        audio_path = _episode_media_path(audio_path_str)

        if audio_path is not None and audio_path.is_file():
            try:
                cues = transcribe_audio(
                    audio_path,
                    model_size=settings.whisper_model_size,
                    language=settings.default_language,
                    prefer_faster_whisper=settings.whisper_prefer_faster,
                )
                if cues:
                    count = _save_transcript_cues(db, episode_id, cues)
                    meta["transcript_source"] = f"whisper_{settings.whisper_model_size}"
                    meta["asr_language"] = settings.default_language
                    meta.pop("transcript_error", None)
                else:
                    meta["transcript_source"] = "asr_empty"
                    meta["transcript_note"] = "Whisper 전사 결과가 비어 있습니다."
            except Exception as exc:  # noqa: BLE001
                meta["transcript_source"] = "asr_failed"
                meta["transcript_error"] = str(exc)[:500]
        else:
            meta["transcript_source"] = "asr_no_audio"
            meta["transcript_note"] = "프록시 오디오 파일을 찾을 수 없어 ASR을 건너뜁니다."
    else:
        meta["transcript_source"] = "none"
        if episode.source_subtitle_path:
            meta["transcript_note"] = (
                "자막 파일 경로가 없거나 로컬에서 찾을 수 없습니다. "
                "새 업로드 시 SRT 또는 WebVTT를 함께 올리면 여기와 미리보기에 반영됩니다."
            )
        else:
            meta["transcript_note"] = (
                "업로드 시 자막(SRT/WebVTT)을 함께 넣으면 타임라인·미리보기에 표시됩니다."
            )

    episode.metadata_json = meta
    mark_analysis_running(episode, "extract_or_generate_transcript")
    mark_analysis_completed(
        episode,
        "extract_or_generate_transcript",
        step_details={"transcript_segment_count": count, "source": meta.get("transcript_source")},
    )
    db.add(episode)
    db.commit()
    return {**payload, "transcript_segment_count": count}


def compute_signals_step(db: Session, payload: dict) -> dict:
    episode_id = payload["episode_id"]
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise ValueError("Episode not found")

    segs = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.episode_id == episode_id)
            .order_by(TranscriptSegment.segment_index.asc())
        )
    )
    shots = list(
        db.scalars(
            select(Shot).where(Shot.episode_id == episode_id).order_by(Shot.shot_index.asc())
        )
    )

    if segs:
        durs = [float(s.end_time) - float(s.start_time) for s in segs]
        durs.sort()
        median_dur = durs[len(durs) // 2]
        total_chars = sum(len((s.text or "").strip()) for s in segs)
        t_span = max(float(s.end_time) for s in segs) - min(float(s.start_time) for s in segs)
        covered = sum(durs)
        speech_ratio = covered / max(t_span, 0.01)
    else:
        median_dur = 0.0
        total_chars = 0
        speech_ratio = 0.0

    meta = dict(episode.metadata_json or {})
    meta["signals"] = {
        "algorithm": "signals_v1",
        "transcript_segment_count": len(segs),
        "median_cue_duration_sec": round(median_dur, 3),
        "total_subtitle_chars": total_chars,
        "estimated_speech_timeline_ratio": round(min(1.0, speech_ratio), 3),
        "shot_count": len(shots),
        "commentary_friendly": speech_ratio > 0.12 and len(segs) >= 3,
    }
    episode.metadata_json = meta
    mark_analysis_running(episode, "compute_signals")
    mark_analysis_completed(
        episode,
        "compute_signals",
        step_details={
            "algorithm": "signals_v1",
            "transcript_segment_count": len(segs),
            "shot_count": len(shots),
        },
    )
    db.add(episode)
    db.commit()
    return payload


def generate_candidates_step(db: Session, payload: dict) -> dict:
    episode_id = payload["episode_id"]
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise ValueError("Episode not found")

    db.execute(delete(Candidate).where(Candidate.episode_id == episode_id))

    mark_analysis_running(episode, "generate_candidates")

    perf: dict[str, object] = {}

    t0 = time.perf_counter()
    scored_windows = build_candidates_for_episode(db, episode_id)
    perf["candidate_gen_ms"] = int((time.perf_counter() - t0) * 1000)

    # 임베딩 시그널 사용 현황 집계
    emb_attempted = sum(
        1 for w in scored_windows
        if isinstance(w.metadata_json, dict) and w.metadata_json.get("embedding_attempted")
    )
    emb_used = sum(
        1 for w in scored_windows
        if isinstance(w.metadata_json, dict) and w.metadata_json.get("embedding_used")
    )
    perf["embedding_signal_windows_used"] = emb_used
    perf["embedding_signal_failures"] = max(0, emb_attempted - emb_used)

    # 오디오 시드 현황 집계
    audio_seeds = [
        w for w in scored_windows
        if isinstance(w.metadata_json, dict) and w.metadata_json.get("candidate_track") == "audio"
    ]
    audio_backends = {
        w.metadata_json.get("audio_seed_backend", "unknown")
        for w in audio_seeds
        if isinstance(w.metadata_json, dict)
    }
    perf["audio_seed_backend"] = ",".join(sorted(audio_backends)) if audio_backends else "none"
    perf["audio_seed_count"] = len(audio_seeds)

    shots = list(db.scalars(select(Shot).where(Shot.episode_id == episode_id)))
    segments = list(db.scalars(select(TranscriptSegment).where(TranscriptSegment.episode_id == episode_id)))
    from app.services.candidate_generation import _episode_timeline_end
    timeline_end = _episode_timeline_end(episode, shots, segments)

    # micro-event 수 계측 (scored_windows source_events 총합)
    micro_event_count = sum(
        len(w.metadata_json.get("source_events") or [])
        for w in scored_windows
        if isinstance(w.metadata_json, dict)
    )
    perf["micro_event_count"] = micro_event_count
    perf["scored_window_count"] = len(scored_windows)

    if micro_event_count > 500:
        logger.warning("[%s] micro_event_count=%d > 500 (O(n²) 위험)", episode_id, micro_event_count)

    t0 = time.perf_counter()
    composite_windows = build_composite_candidates(scored_windows, timeline_end=timeline_end)
    perf["composite_gen_ms"] = int((time.perf_counter() - t0) * 1000)
    perf["composite_count"] = len(composite_windows)

    if perf["composite_gen_ms"] > 30000:
        logger.warning("[%s] composite_gen_ms=%d > 30000ms", episode_id, perf["composite_gen_ms"])

    # contiguous 우선 원칙: contiguous complete arc가 있으면 composite에
    # composite_advantage_reason이 없는 한 감점
    best_contiguous_arc = max(
        (float(w.metadata_json.get("single_arc_complete_score", 0.0)) for w in scored_windows),
        default=0.0,
    )
    for cw in composite_windows:
        meta = dict(cw.metadata_json)
        arc_payoff = float(meta.get("arc_payoff_strength", 0.0))
        if best_contiguous_arc >= 0.3 and arc_payoff < best_contiguous_arc * 1.2:
            cw_score = cw.total_score * 0.9
            meta["composite_advantage_reason"] = "contiguous_preferred"
        else:
            cw_score = cw.total_score
            meta["composite_advantage_reason"] = "composite_arc_stronger"
        scored_windows.append(ScoredWindow(
            start_time=cw.start_time,
            end_time=cw.end_time,
            total_score=round(cw_score, 2),
            scores_json=cw.scores_json,
            title_hint=cw.title_hint,
            metadata_json=meta,
        ))

    t0 = time.perf_counter()
    scored_windows = rerank_candidates_for_episode(
        scored_windows,
        provider="heuristic_noop",
        reason="pre_vision_candidate_rerank_hook",
    )
    perf["rerank_ms"] = int((time.perf_counter() - t0) * 1000)

    t0 = time.perf_counter()
    scored_windows, vision_summary = refine_candidates_with_vision(
        db,
        episode,
        scored_windows,
        ignore_cache=bool(payload.get("ignore_cache")),
    )
    perf["vision_rerank_ms"] = int((time.perf_counter() - t0) * 1000)

    if perf["vision_rerank_ms"] > 120000:
        logger.warning("[%s] vision_rerank_ms=%d > 120000ms", episode_id, perf["vision_rerank_ms"])

    scored_windows = dedupe_scored_windows(scored_windows)
    perf["final_candidate_count"] = len(scored_windows)
    for index, sw in enumerate(scored_windows, start=1):
        hint = sw.title_hint[:255] if len(sw.title_hint) > 255 else sw.title_hint
        clip_spans = sw.metadata_json.get("clip_spans") if isinstance(sw.metadata_json, dict) else None
        duration_seconds = (
            clip_spans_total_duration(clip_spans) if isinstance(clip_spans, list) and clip_spans else round(sw.end_time - sw.start_time, 3)
        )
        db.add(
            Candidate(
                episode_id=episode_id,
                candidate_index=index,
                type="context_commentary",
                status=CandidateStatus.GENERATED.value,
                title_hint=hint,
                start_time=sw.start_time,
                end_time=sw.end_time,
                duration_seconds=duration_seconds,
                total_score=sw.total_score,
                scores_json=sw.scores_json,
                metadata_json=sw.metadata_json,
            )
        )

    meta = dict(episode.metadata_json or {})
    meta["vision_rerank"] = vision_summary
    meta["candidate_gen_perf"] = perf
    episode.metadata_json = meta
    episode.status = EpisodeStatus.READY.value
    mark_analysis_completed(
        episode,
        "generate_candidates",
        step_details={
            "candidate_count": len(scored_windows),
            "vision_status": vision_summary.get("status"),
            "vision_applied_candidates": vision_summary.get("applied_candidates", 0),
        },
        pipeline_status="ready",
    )
    db.add(episode)
    db.commit()

    candidate_count = db.scalar(
        select(func.count(Candidate.id)).where(Candidate.episode_id == episode_id)
    )
    return {"episode_id": episode_id, "candidate_count": candidate_count}


def candidate_segments(db: Session, candidate: Candidate) -> list[TranscriptSegment]:
    spans = candidate_clip_spans(candidate)
    segments = list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.episode_id == candidate.episode_id)
            .order_by(TranscriptSegment.start_time.asc())
        )
    )
    return [
        segment
        for segment in segments
        if any(
            float(segment.start_time) <= span["end_time"] and float(segment.end_time) >= span["start_time"]
            for span in spans
        )
    ]


def candidate_shots(db: Session, candidate: Candidate) -> list[Shot]:
    spans = candidate_clip_spans(candidate)
    shots = list(
        db.scalars(
            select(Shot).where(Shot.episode_id == candidate.episode_id).order_by(Shot.shot_index.asc())
        )
    )
    return [
        shot
        for shot in shots
        if any(
            float(shot.start_time) <= span["end_time"] and float(shot.end_time) >= span["start_time"]
            for span in spans
        )
    ]
