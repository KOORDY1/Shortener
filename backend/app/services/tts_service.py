from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import TypedDict

import httpx

from app.core.config import get_settings
from app.services.audio_probe import probe_audio_duration_seconds


class TTSResult(TypedDict):
    path: str
    provider: str
    voice_key: str
    fallback_reason: str | None
    requested_duration_sec: float
    actual_audio_duration_sec: float
    final_segment_duration_sec: float


def _sanitize_voice(voice_key: str | None) -> str:
    raw = (voice_key or "").strip().lower()
    if raw in {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}:
        return raw
    if raw in {"ko_female_01", "female", "default"}:
        return "alloy"
    return "alloy"


def _ffmpeg_silence(path: Path, duration_sec: float) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is required to synthesize fallback silence")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        str(duration_sec),
        "-c:a",
        "aac",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)


def _normalize_audio_duration(
    input_path: Path,
    *,
    output_path: Path,
    requested_duration_sec: float,
    actual_duration_sec: float | None,
) -> tuple[Path, float]:
    target_duration = max(0.0, float(requested_duration_sec))
    measured_duration = float(actual_duration_sec or 0.0)
    if target_duration <= 0:
        return input_path, max(0.0, measured_duration)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not measured_duration:
        _ffmpeg_silence(output_path, target_duration)
        return output_path, target_duration
    if abs(measured_duration - target_duration) <= 0.08:
        return input_path, round(measured_duration, 3)
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-af",
        f"apad=pad_dur={target_duration},atrim=0:{target_duration}",
        "-c:a",
        "aac",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return output_path, target_duration


def synthesize_short_tts(
    *,
    text: str,
    output_path: Path,
    voice_key: str | None,
    duration_sec: float,
) -> TTSResult:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    normalized_voice = _sanitize_voice(voice_key)
    cleaned_text = " ".join(text.strip().split())

    if cleaned_text and settings.openai_api_key:
        try:
            response = httpx.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                },
                json={
                    "model": "gpt-4o-mini-tts",
                    "voice": normalized_voice,
                    "input": cleaned_text,
                    "format": "mp3",
                },
                timeout=120.0,
            )
            response.raise_for_status()
            output_path.write_bytes(response.content)
            actual_duration = probe_audio_duration_seconds(output_path)
            normalized_path, final_duration = _normalize_audio_duration(
                output_path,
                output_path=output_path.with_suffix(".m4a"),
                requested_duration_sec=duration_sec,
                actual_duration_sec=actual_duration,
            )
            return {
                "path": str(normalized_path.resolve()),
                "provider": "openai_tts",
                "voice_key": normalized_voice,
                "fallback_reason": None,
                "requested_duration_sec": duration_sec,
                "actual_audio_duration_sec": actual_duration or duration_sec,
                "final_segment_duration_sec": final_duration,
            }
        except Exception as exc:
            _ffmpeg_silence(output_path.with_suffix(".m4a"), duration_sec)
            silent_path = output_path.with_suffix(".m4a")
            return {
                "path": str(silent_path.resolve()),
                "provider": "silent_fallback",
                "voice_key": normalized_voice,
                "fallback_reason": str(exc)[:500],
                "requested_duration_sec": duration_sec,
                "actual_audio_duration_sec": duration_sec,
                "final_segment_duration_sec": duration_sec,
            }

    silent_path = output_path.with_suffix(".m4a")
    reason = "missing_openai_api_key" if cleaned_text else "empty_tts_text"
    _ffmpeg_silence(silent_path, duration_sec)
    return {
        "path": str(silent_path.resolve()),
        "provider": "silent_fallback",
        "voice_key": normalized_voice,
        "fallback_reason": reason,
        "requested_duration_sec": duration_sec,
        "actual_audio_duration_sec": duration_sec,
        "final_segment_duration_sec": duration_sec,
    }
