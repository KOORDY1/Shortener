from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


def _parse_float(value: object) -> float | None:
    if value in (None, "", "N/A"):
        return None
    try:
        parsed = float(str(value))
    except (TypeError, ValueError):
        return None
    if parsed < 0:
        return None
    return parsed


def _parse_int(value: object) -> int | None:
    if value in (None, "", "N/A"):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _parse_fps(value: object) -> float | None:
    if value in (None, "", "0/0", "N/A"):
        return None
    text = str(value)
    if "/" in text:
        raw_num, raw_den = text.split("/", 1)
        try:
            num = float(raw_num)
            den = float(raw_den)
        except ValueError:
            return None
        if den == 0:
            return None
        fps = num / den
    else:
        try:
            fps = float(text)
        except ValueError:
            return None
    return round(fps, 3) if fps > 0 else None


def probe_media_metadata(video_path: Path) -> dict[str, object]:
    path = video_path.expanduser()
    summary: dict[str, object] = {
        "status": "unknown",
        "error": None,
        "duration_seconds": None,
        "fps": None,
        "width": None,
        "height": None,
        "video_stream_found": False,
    }

    if not path.is_file():
        summary["status"] = "file_missing"
        summary["error"] = "source video file not found"
        return summary

    if shutil.which("ffprobe") is None:
        summary["status"] = "ffprobe_missing"
        summary["error"] = "ffprobe binary is not available"
        return summary

    try:
        completed = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or exc.stdout or str(exc)).strip()
        summary["status"] = "ffprobe_failed"
        summary["error"] = stderr[:500] or "ffprobe exited with non-zero status"
        return summary
    except OSError as exc:
        summary["status"] = "ffprobe_failed"
        summary["error"] = str(exc)[:500]
        return summary

    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        summary["status"] = "invalid_output"
        summary["error"] = f"failed to parse ffprobe output: {exc}"
        return summary

    format_payload = payload.get("format") or {}
    streams = payload.get("streams") or []
    duration_seconds = _parse_float(format_payload.get("duration"))
    if duration_seconds is not None:
        summary["duration_seconds"] = round(duration_seconds, 3)

    video_stream = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        summary["status"] = "no_video_stream"
        summary["error"] = "ffprobe did not return a video stream"
        return summary

    summary["video_stream_found"] = True
    summary["width"] = _parse_int(video_stream.get("width"))
    summary["height"] = _parse_int(video_stream.get("height"))
    summary["fps"] = _parse_fps(video_stream.get("avg_frame_rate")) or _parse_fps(
        video_stream.get("r_frame_rate")
    )
    summary["status"] = "ok"
    return summary
