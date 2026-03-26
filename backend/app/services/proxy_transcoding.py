from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.db.models import Episode
from app.services.cache_utils import file_signature, stable_hash
from app.services.shot_detection import ffprobe_duration_seconds, resolve_source_video_path
from app.services.storage_service import episode_root


def _proxy_output_paths(episode_id: str) -> tuple[Path, Path]:
    root = episode_root(episode_id)
    return root / "proxy" / "analysis_proxy.mp4", root / "audio" / "analysis_audio.m4a"


def _transcode_profile() -> dict[str, Any]:
    settings = get_settings()
    return {
        "version": settings.proxy_transcode_version,
        "max_width": int(settings.proxy_max_width),
        "fps": int(settings.proxy_video_fps),
        "crf": int(settings.proxy_video_crf),
        "audio_bitrate_kbps": int(settings.proxy_audio_bitrate_kbps),
    }


def _proxy_cache_key(source_path: Path) -> str:
    return stable_hash(
        {
            "source": file_signature(source_path),
            "profile": _transcode_profile(),
        }
    )


def _is_valid_media(path: Path) -> bool:
    return path.is_file() and path.stat().st_size >= 2048


def _build_proxy_video(source_path: Path, target_path: Path) -> bool:
    settings = get_settings()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    vf = f"fps={int(settings.proxy_video_fps)},scale='min(iw,{int(settings.proxy_max_width)})':-2"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-an",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(int(settings.proxy_video_crf)),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(target_path),
        ],
        capture_output=True,
        timeout=7200,
        check=False,
    )
    return proc.returncode == 0 and _is_valid_media(target_path)


def _build_proxy_audio(source_path: Path, target_path: Path) -> bool:
    settings = get_settings()
    target_path.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            f"{int(settings.proxy_audio_bitrate_kbps)}k",
            str(target_path),
        ],
        capture_output=True,
        timeout=7200,
        check=False,
    )
    return proc.returncode == 0 and _is_valid_media(target_path)


def ensure_analysis_proxy(episode: Episode, *, ignore_cache: bool = False) -> dict[str, Any]:
    settings = get_settings()
    source_path = resolve_source_video_path(episode)
    summary: dict[str, Any] = {
        "version": settings.proxy_transcode_version,
        "status": "fallback",
        "mode": "source_video",
        "profile": _transcode_profile(),
    }
    if not source_path.is_file():
        summary["reason"] = "missing_source_video"
        return summary
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        summary["reason"] = "ffmpeg_missing"
        return summary

    proxy_path, audio_path = _proxy_output_paths(episode.id)
    cache_key = _proxy_cache_key(source_path)
    meta = dict(episode.metadata_json or {})
    existing = dict(meta.get("proxy_transcode") or {})
    if not ignore_cache and (
        existing.get("cache_key") == cache_key
        and _is_valid_media(proxy_path)
        and _is_valid_media(audio_path)
    ):
        episode.proxy_video_path = str(proxy_path.resolve())
        episode.audio_path = str(audio_path.resolve())
        duration = ffprobe_duration_seconds(proxy_path)
        if duration and duration > 0:
            episode.duration_seconds = round(duration, 3)
        return {
            **existing,
            "status": "cached",
            "mode": "analysis_proxy_cached",
        }

    proxy_ok = _build_proxy_video(source_path, proxy_path)
    audio_ok = _build_proxy_audio(source_path, audio_path)
    if proxy_ok:
        episode.proxy_video_path = str(proxy_path.resolve())
        duration = ffprobe_duration_seconds(proxy_path)
        if duration and duration > 0:
            episode.duration_seconds = round(duration, 3)
    else:
        episode.proxy_video_path = str(source_path.resolve())
    if audio_ok:
        episode.audio_path = str(audio_path.resolve())
    else:
        episode.audio_path = None

    summary.update(
        {
            "cache_key": cache_key,
            "status": "completed" if proxy_ok else "fallback",
            "mode": "analysis_proxy" if proxy_ok else "source_video_fallback",
            "source": file_signature(source_path),
            "proxy_path": episode.proxy_video_path,
            "audio_path": episode.audio_path,
            "audio_generated": audio_ok,
        }
    )
    if not proxy_ok:
        summary["reason"] = "proxy_transcode_failed"
    return summary
