"""FFmpeg scene 필터로 컷 시각을 검출하고 샷 구간·썸네일을 만듭니다."""

from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.db.models import Episode
from app.services.cache_utils import file_signature, stable_hash

PTS_TIME_RE = re.compile(r"pts_time\s*:\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
MAX_SHOTS = 100
MIN_SHOT_SEC = 0.35
MERGE_CUT_GAP_SEC = 0.28


def resolve_source_video_path(episode: Episode) -> Path:
    settings = get_settings()
    raw = Path(episode.source_video_path).expanduser()
    path = raw.resolve() if raw.is_absolute() else (settings.resolved_storage_root / raw).resolve()
    return path


def resolve_proxy_video_path(episode: Episode) -> Path | None:
    if not episode.proxy_video_path:
        return None
    settings = get_settings()
    raw = Path(episode.proxy_video_path).expanduser()
    path = raw.resolve() if raw.is_absolute() else (settings.resolved_storage_root / raw).resolve()
    return path


def resolve_analysis_video_path(episode: Episode) -> tuple[Path, str]:
    proxy = resolve_proxy_video_path(episode)
    if proxy is not None and proxy.is_file() and proxy.stat().st_size >= 2048:
        return proxy, "proxy_video"
    return resolve_source_video_path(episode), "source_video"


def shot_detection_cache_key(episode: Episode) -> tuple[str, Path, str]:
    settings = get_settings()
    video_path, source_kind = resolve_analysis_video_path(episode)
    cache_key = stable_hash(
        {
            "video": file_signature(video_path),
            "source_kind": source_kind,
            "scene_threshold": float(settings.ffmpeg_scene_threshold),
            "max_shots": MAX_SHOTS,
            "min_shot_sec": MIN_SHOT_SEC,
            "merge_cut_gap_sec": MERGE_CUT_GAP_SEC,
        }
    )
    return cache_key, video_path, source_kind


def serialize_shot_intervals(intervals: list[tuple[float, float]]) -> list[dict[str, float]]:
    return [
        {"start_time": round(float(start_time), 3), "end_time": round(float(end_time), 3)}
        for start_time, end_time in intervals
    ]


def deserialize_shot_intervals(items: list[dict[str, Any]] | None) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        try:
            start_time = float(item["start_time"])
            end_time = float(item["end_time"])
        except (KeyError, TypeError, ValueError):
            continue
        if end_time > start_time:
            out.append((round(start_time, 3), round(end_time, 3)))
    return out


def ffprobe_duration_seconds(video_path: Path) -> float | None:
    try:
        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if proc.returncode != 0:
            return None
        line = (proc.stdout or "").strip().splitlines()[0] if proc.stdout else ""
        return float(line) if line else None
    except (OSError, ValueError, IndexError):
        return None


def ffmpeg_scene_cut_times(video_path: Path, threshold: float) -> list[float]:
    """scene 점수가 threshold를 넘는 프레임의 pts_time 목록."""
    vf = f"select='gt(scene\\,{threshold})',showinfo"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-loglevel",
            "info",
            "-i",
            str(video_path),
            "-vf",
            vf,
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=3600,
        check=False,
    )
    text = (proc.stderr or "") + "\n" + (proc.stdout or "")
    times: list[float] = []
    for m in PTS_TIME_RE.finditer(text):
        try:
            times.append(float(m.group(1)))
        except ValueError:
            continue
    times.sort()
    merged: list[float] = []
    for t in times:
        if not merged or t - merged[-1] >= MERGE_CUT_GAP_SEC:
            merged.append(t)
    return merged


def cuts_to_shot_intervals(cut_times: list[float], duration: float) -> list[tuple[float, float]]:
    if duration <= 0:
        return []
    points = [0.0]
    for t in cut_times:
        if MERGE_CUT_GAP_SEC < t < duration - MERGE_CUT_GAP_SEC:
            points.append(t)
    points.append(duration)
    points = sorted(set(round(p, 4) for p in points))
    intervals: list[tuple[float, float]] = []
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        if b - a >= MIN_SHOT_SEC:
            intervals.append((round(a, 3), round(b, 3)))
    if not intervals and duration > 0:
        intervals.append((0.0, round(duration, 3)))
    return intervals


def _merge_intervals_to_max_count(
    intervals: list[tuple[float, float]], max_count: int
) -> list[tuple[float, float]]:
    if len(intervals) <= max_count:
        return intervals
    group = int(math.ceil(len(intervals) / max_count))
    out: list[tuple[float, float]] = []
    i = 0
    while i < len(intervals):
        chunk = intervals[i : i + group]
        out.append((chunk[0][0], chunk[-1][1]))
        i += group
    return out


def equal_split_shots(duration: float, count: int = 14) -> list[tuple[float, float]]:
    duration = max(12.0, duration)
    w = duration / count
    return [(round(i * w, 3), round(min(duration, (i + 1) * w), 3)) for i in range(count)]


def extract_shot_thumbnail(video_path: Path, start_sec: float, out_path: Path) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    t = max(0.0, start_sec + 0.05)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            str(t),
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "5",
            str(out_path),
        ],
        capture_output=True,
        timeout=90,
        check=False,
    )
    return proc.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 80


def detect_shot_intervals_for_episode(
    episode: Episode,
) -> tuple[list[tuple[float, float]], str, str]:
    """
    Returns (list of (start,end), mode tag).
    mode: ffmpeg_scene | equal_split_invalid_file | equal_split_no_ffmpeg | equal_split_fallback
    """
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        d = float(episode.duration_seconds or 40.0)
        return equal_split_shots(d), "equal_split_no_ffmpeg", "source_video"

    video, source_kind = resolve_analysis_video_path(episode)
    if not video.is_file() or video.stat().st_size < 2048:
        d = float(episode.duration_seconds or 40.0)
        return equal_split_shots(d), "equal_split_invalid_file", source_kind

    duration = ffprobe_duration_seconds(video)
    if duration is None or duration <= 0:
        duration = float(episode.duration_seconds or 40.0)
        return equal_split_shots(duration), "equal_split_no_duration", source_kind

    settings = get_settings()
    thr = float(settings.ffmpeg_scene_threshold)
    cuts = ffmpeg_scene_cut_times(video, thr)
    intervals = cuts_to_shot_intervals(cuts, duration)

    if not intervals:
        intervals = equal_split_shots(duration, count=max(8, min(20, int(duration / 5.0) or 12)))

    intervals = _merge_intervals_to_max_count(intervals, MAX_SHOTS)
    mode = "ffmpeg_scene" if cuts else "equal_split_no_scene_peaks"
    return intervals, mode, source_kind
