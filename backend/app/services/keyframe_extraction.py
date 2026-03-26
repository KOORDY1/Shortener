from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

from app.core.config import get_settings
from app.db.models import Episode, Shot
from app.services.cache_utils import file_signature, stable_hash
from app.services.shot_detection import resolve_source_video_path
from app.services.storage_service import episode_root

LONG_SHOT_THRESHOLD_SEC = 12.0
MIN_FRAME_GAP_SEC = 0.12


def _resolve_video_candidate(path_str: str | None) -> Path | None:
    if not path_str:
        return None
    settings = get_settings()
    raw = Path(path_str).expanduser()
    path = raw.resolve() if raw.is_absolute() else (settings.resolved_storage_root / raw).resolve()
    if not path.is_file() or path.stat().st_size < 2048:
        return None
    return path


def resolve_keyframe_video_path(episode: Episode) -> tuple[Path | None, str]:
    proxy = _resolve_video_candidate(episode.proxy_video_path)
    if proxy is not None:
        return proxy, "proxy_video"
    source = _resolve_video_candidate(episode.source_video_path)
    if source is not None:
        return source, "source_video"
    fallback = resolve_source_video_path(episode)
    if fallback.is_file() and fallback.stat().st_size >= 2048:
        return fallback, "source_video_fallback"
    return None, "missing_video"


def _clean_existing_keyframe_dirs(episode_id: str) -> None:
    shots_root = episode_root(episode_id) / "shots"
    if not shots_root.is_dir():
        return
    for child in shots_root.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)


def _frame_timestamps_for_shot(start_time: float, end_time: float) -> list[float]:
    duration = max(0.0, float(end_time) - float(start_time))
    if duration <= 0:
        return []
    if duration >= LONG_SHOT_THRESHOLD_SEC:
        ratios = (0.05, 0.5, 0.95)
    else:
        ratios = (0.5,)

    edge_pad = min(max(duration * 0.02, 0.04), MIN_FRAME_GAP_SEC)
    out: list[float] = []
    seen: set[int] = set()
    for ratio in ratios:
        ts = float(start_time) + duration * ratio
        ts = min(float(end_time) - edge_pad, max(float(start_time) + edge_pad, ts))
        key = int(round(ts * 1000))
        if key in seen:
            continue
        seen.add(key)
        out.append(round(ts, 3))
    return out


def _extract_frame(video_path: Path, timestamp: float, out_path: Path, max_width: int) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"scale=min(iw\\,{max_width}):-2"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(max(0.0, timestamp)),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            vf,
            "-q:v",
            "5",
            str(out_path),
        ],
        capture_output=True,
        timeout=90,
        check=False,
    )
    return proc.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 80


def _keyframe_cache_key(episode: Episode, shots: Sequence[Shot], video_path: Path | None) -> str:
    settings = get_settings()
    payload = {
        "version": settings.vision_scan_version,
        "video": file_signature(video_path),
        "image_max_width": int(settings.vision_image_max_width),
        "shots": [
            {
                "shot_index": int(shot.shot_index),
                "start_time": round(float(shot.start_time), 3),
                "end_time": round(float(shot.end_time), 3),
            }
            for shot in shots
        ],
    }
    return stable_hash(payload)


def _existing_frame_count(episode_id: str, shots: Sequence[Shot]) -> tuple[int, int]:
    shots_with_keyframes = 0
    frame_count = 0
    for shot in shots:
        shot_dir = episode_root(episode_id) / "shots" / f"{int(shot.shot_index):04d}"
        if not shot_dir.is_dir():
            continue
        files = [
            path
            for path in shot_dir.glob("frame_*.jpg")
            if path.is_file() and path.stat().st_size > 80
        ]
        if files:
            shots_with_keyframes += 1
            frame_count += len(files)
    return shots_with_keyframes, frame_count


def extract_keyframes_for_episode(
    episode: Episode,
    shots: Sequence[Shot],
    *,
    ignore_cache: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    version = str(settings.vision_scan_version or "vision_scan_v1")
    summary: dict[str, Any] = {
        "version": version,
        "status": "skipped",
        "video_source": None,
        "shot_count": len(shots),
        "shots_with_keyframes": 0,
        "frame_count": 0,
        "max_width": int(settings.vision_image_max_width),
    }
    if not shots:
        summary["reason"] = "no_shots"
        return summary
    if not shutil.which("ffmpeg"):
        summary["reason"] = "ffmpeg_missing"
        return summary

    video_path, video_source = resolve_keyframe_video_path(episode)
    summary["video_source"] = video_source
    if video_path is None:
        summary["reason"] = "video_unavailable"
        return summary

    cache_key = _keyframe_cache_key(episode, shots, video_path)
    summary["cache_key"] = cache_key
    existing = dict((episode.metadata_json or {}).get("vision_scan") or {})
    if not ignore_cache and existing.get("cache_key") == cache_key:
        shots_with_keyframes, frame_count = _existing_frame_count(episode.id, shots)
        if shots_with_keyframes == len(shots) and frame_count > 0:
            return {
                **existing,
                "status": "cached",
                "shot_count": len(shots),
                "shots_with_keyframes": shots_with_keyframes,
                "frame_count": frame_count,
                "video_source": video_source,
            }

    _clean_existing_keyframe_dirs(episode.id)

    saved_frames = 0
    shots_with_frames = 0
    for shot in shots:
        timestamps = _frame_timestamps_for_shot(float(shot.start_time), float(shot.end_time))
        if not timestamps:
            continue
        shot_dir = episode_root(episode.id) / "shots" / f"{int(shot.shot_index):04d}"
        shot_saved = 0
        for frame_index, ts in enumerate(timestamps, start=1):
            out_path = shot_dir / f"frame_{frame_index:02d}.jpg"
            if _extract_frame(
                video_path, ts, out_path, max_width=int(settings.vision_image_max_width)
            ):
                shot_saved += 1
                saved_frames += 1
        if shot_saved > 0:
            shots_with_frames += 1

    summary["shots_with_keyframes"] = shots_with_frames
    summary["frame_count"] = saved_frames
    if saved_frames > 0:
        summary["status"] = "completed"
    else:
        summary["status"] = "fallback"
        summary["reason"] = "frame_extraction_failed"
    return summary
