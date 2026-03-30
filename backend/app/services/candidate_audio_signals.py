"""Track C: audio-reaction candidate seed 생성.

FFmpeg astats/volumedetect로 segment-level RMS/peak를 추출해
silence→spike, burst, 에너지 급변 구간을 후보로 올린다.
FFmpeg 없거나 오디오 파일이 없으면 graceful fallback (빈 목록).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

MIN_AUDIO_WINDOW_SEC = 30.0
MAX_AUDIO_WINDOW_SEC = 90.0
MAX_AUDIO_SEEDS = 10
SEGMENT_LENGTH_SEC = 5.0

_EBUR128_RE = re.compile(
    r"t:\s*([\d.]+)\s+M:\s*([-\d.]+)\s+S:\s*([-\d.]+)\s+I:\s*([-\d.]+)",
    re.IGNORECASE,
)


def _parse_rms_levels(stderr_text: str) -> list[float]:
    """FFmpeg astats 출력에서 RMS_level 값을 dB 단위로 추출."""
    pattern = re.compile(r"RMS\s+level\s+dB:\s*([-\d.]+)", re.IGNORECASE)
    values: list[float] = []
    for match in pattern.finditer(stderr_text):
        try:
            values.append(float(match.group(1)))
        except ValueError:
            continue
    return values


def extract_audio_energy_profile(
    audio_path: Path,
    duration_seconds: float,
    segment_length: float = SEGMENT_LENGTH_SEC,
) -> list[dict]:
    """오디오 파일을 segment_length 단위로 나눠 RMS 에너지를 측정한다.

    Returns list of {"start": float, "end": float, "rms_db": float}.
    실패하면 빈 목록.
    """
    if not audio_path.is_file() or audio_path.stat().st_size < 1024:
        return []
    if not shutil.which("ffmpeg"):
        return []

    segments: list[dict] = []
    t = 0.0
    while t < duration_seconds:
        seg_end = min(t + segment_length, duration_seconds)
        try:
            proc = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "info",
                    "-ss", str(t),
                    "-t", str(seg_end - t),
                    "-i", str(audio_path),
                    "-af", "astats=metadata=1:reset=0",
                    "-f", "null",
                    "-",
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            rms_values = _parse_rms_levels(proc.stderr or "")
            rms_db = max(rms_values) if rms_values else -60.0
        except (OSError, subprocess.TimeoutExpired):
            rms_db = -60.0

        segments.append({
            "start": round(t, 3),
            "end": round(seg_end, 3),
            "rms_db": round(rms_db, 1),
        })
        t = seg_end

    return segments


def compute_audio_impact_scores(energy_profile: list[dict]) -> list[dict]:
    """에너지 프로파일에 silence_to_spike, burst, variance 점수를 추가한다."""
    if not energy_profile:
        return []

    rms_values = [seg["rms_db"] for seg in energy_profile]
    mean_rms = sum(rms_values) / max(len(rms_values), 1)

    scored: list[dict] = []
    for i, seg in enumerate(energy_profile):
        rms = seg["rms_db"]
        prev_rms = energy_profile[i - 1]["rms_db"] if i > 0 else rms

        silence_to_spike = 0.0
        if prev_rms < -40.0 and rms > -25.0:
            silence_to_spike = min(1.0, (rms - prev_rms) / 30.0)

        energy_burst = 0.0
        if mean_rms < -10.0 and rms > mean_rms + 10.0:
            energy_burst = min(1.0, (rms - mean_rms) / 20.0)

        volume_jump = min(1.0, abs(rms - prev_rms) / 25.0) if i > 0 else 0.0

        impact = min(
            1.0,
            silence_to_spike * 0.4 + energy_burst * 0.35 + volume_jump * 0.25,
        )
        scored.append({
            **seg,
            "silence_to_spike": round(silence_to_spike, 3),
            "energy_burst": round(energy_burst, 3),
            "volume_jump": round(volume_jump, 3),
            "audio_impact": round(impact, 3),
        })

    return scored


def _parse_ebur128_output(stderr_text: str, segment_length: float = SEGMENT_LENGTH_SEC) -> list[dict]:
    """FFmpeg ebur128 출력을 파싱해 segment-level 라우드니스 프로파일을 반환한다.

    ebur128 출력 예:
        t: 5.00 M: -18.2 S: -20.1 I: -23.0 LRA: 5.0
    segment_length 간격으로 그룹화해 평균 momentary 라우드니스를 rms_db로 사용한다.
    """
    frames: list[tuple[float, float]] = []  # (time, momentary_loudness)
    for m in _EBUR128_RE.finditer(stderr_text):
        try:
            t = float(m.group(1))
            momentary = float(m.group(2))
            frames.append((t, momentary))
        except ValueError:
            continue

    if not frames:
        return []

    # segment_length 단위로 묶어서 평균 계산
    max_time = frames[-1][0]
    segments: list[dict] = []
    t = 0.0
    while t < max_time:
        seg_end = t + segment_length
        window_frames = [val for ts, val in frames if t <= ts < seg_end]
        rms_db = (sum(window_frames) / len(window_frames)) if window_frames else -70.0
        segments.append({
            "start": round(t, 3),
            "end": round(seg_end, 3),
            "rms_db": round(rms_db, 1),
        })
        t = seg_end

    return segments


def extract_audio_energy_profile_v2(
    audio_path: Path,
    duration_seconds: float,
    segment_length: float = SEGMENT_LENGTH_SEC,
) -> list[dict]:
    """단일 FFmpeg ebur128 호출로 전체 오디오 에너지 프로파일을 추출한다.

    기존 extract_audio_energy_profile()과 같은 반환 형식이지만
    단일 프로세스로 N/100 이하의 처리 시간.

    Returns list of {"start": float, "end": float, "rms_db": float}.
    실패하면 기존 astats 방식으로 폴백.
    """
    if not audio_path.is_file() or audio_path.stat().st_size < 1024:
        return []
    if not shutil.which("ffmpeg"):
        return []

    try:
        proc = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-i", str(audio_path),
                "-af", "ebur128=framelog=verbose",
                "-f", "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        segments = _parse_ebur128_output(proc.stderr or "", segment_length=segment_length)
        if segments:
            return segments
    except (OSError, subprocess.TimeoutExpired):
        pass

    # ebur128 실패 시 기존 astats 방식으로 폴백
    return extract_audio_energy_profile(audio_path, duration_seconds, segment_length)


def generate_audio_seeds_v2(
    audio_path: Path | None,
    duration_seconds: float,
) -> list[dict]:
    """Audio-reaction track 씨앗 생성 v2: ebur128 단일 호출 방식."""
    if audio_path is None:
        return []

    energy_profile = extract_audio_energy_profile_v2(Path(audio_path), duration_seconds)
    if not energy_profile:
        return []

    scored_segments = compute_audio_impact_scores(energy_profile)
    if not scored_segments:
        return []

    seeds: list[dict] = []
    seen: set[tuple[int, int]] = set()
    high_impact = [s for s in scored_segments if s["audio_impact"] >= 0.2]

    for anchor in high_impact:
        anchor_time = anchor["start"]
        for pre_pad in (3.0, 6.0, 10.0):
            for post_pad in (5.0, 10.0, 20.0):
                start_time = max(0.0, anchor_time - pre_pad)
                end_time = min(
                    duration_seconds,
                    anchor_time + anchor["end"] - anchor["start"] + post_pad,
                )
                window_duration = end_time - start_time
                if window_duration < MIN_AUDIO_WINDOW_SEC or window_duration > MAX_AUDIO_WINDOW_SEC:
                    continue
                key = (int(round(start_time * 10)), int(round(end_time * 10)))
                if key in seen:
                    continue
                seen.add(key)
                window_segments = [
                    s for s in scored_segments
                    if s["start"] < end_time and s["end"] > start_time
                ]
                if not window_segments:
                    continue
                max_impact = max(s["audio_impact"] for s in window_segments)
                seeds.append({
                    "start_time": round(start_time, 3),
                    "end_time": round(end_time, 3),
                    "window_reason": "audio_reaction",
                    "candidate_track": "audio",
                    "audio_impact_score": round(max_impact, 3),
                    "anchor_time": round(anchor_time, 3),
                })

    seeds.sort(key=lambda s: s["audio_impact_score"], reverse=True)
    return seeds[:MAX_AUDIO_SEEDS]


def _apply_advanced_feature_corrections(
    seeds: list[dict],
    features: list[dict],
) -> list[dict]:
    """librosa 특징으로 seed audio_impact_score를 소폭 보정한다.

    - tension_hint > 0.5: 소폭 보너스 (+tension * 0.1)
    - speech_likelihood < 0.2 (BGM/음악 지배): 과도한 보너스 억제 (×0.85)
    spectral_centroid 필드가 없으면 (ffmpeg 결과) 원본 반환.
    """
    if not features or "tension_hint" not in features[0]:
        return seeds

    corrected: list[dict] = []
    for seed in seeds:
        start = float(seed["start_time"])
        end = float(seed["end_time"])
        window_feats = [f for f in features if float(f["start"]) < end and float(f["end"]) > start]
        if not window_feats:
            corrected.append(seed)
            continue

        avg_tension = sum(float(f.get("tension_hint", 0.0)) for f in window_feats) / len(window_feats)
        avg_speech = sum(float(f.get("speech_likelihood", 0.0)) for f in window_feats) / len(window_feats)

        impact = float(seed.get("audio_impact_score", 0.0))
        if avg_tension > 0.5:
            impact = min(1.0, impact + avg_tension * 0.1)
        if avg_speech < 0.2:
            impact = impact * 0.85

        corrected.append({
            **seed,
            "audio_impact_score": round(impact, 3),
            "avg_tension_hint": round(avg_tension, 3),
            "avg_speech_likelihood": round(avg_speech, 3),
        })

    return corrected


def generate_audio_seeds_live(
    audio_path: Path | None,
    duration_seconds: float,
    *,
    backend: str = "ffmpeg",
    librosa_enabled: bool = False,
) -> list[dict]:
    """Track C 메인 진입점. ebur128 v2를 기본 경로로 사용.

    Args:
        audio_path: 오디오 파일 경로. None이면 빈 목록 반환.
        duration_seconds: 에피소드 길이 (초).
        backend: "ffmpeg" | "librosa" | "auto"
        librosa_enabled: True면 librosa 특징 추출을 강제 시도.

    각 seed dict에 audio_seed_backend, audio_profile_segment_count,
    audio_feature_backend 필드가 추가된다.
    """
    if audio_path is None:
        return []

    seeds = generate_audio_seeds_v2(audio_path, duration_seconds)
    audio_backend = "ebur128_v2"

    if not seeds:
        seeds = generate_audio_seeds(audio_path, duration_seconds)
        audio_backend = "astats_fallback"

    # optional librosa 보정
    if seeds and (librosa_enabled or backend in ("librosa", "auto")):
        try:
            from app.services.audio_analysis_service import (  # local import — optional dep
                compute_audio_emotion_scores,
                extract_audio_features,
            )
            adv_backend = backend if backend in ("librosa", "auto") else "auto"
            features = extract_audio_features(audio_path, backend=adv_backend)
            if features:
                emotion_features = compute_audio_emotion_scores(features)
                if emotion_features and "tension_hint" in emotion_features[0]:
                    seeds = _apply_advanced_feature_corrections(seeds, emotion_features)
                    audio_backend = "librosa"
        except Exception:
            pass  # librosa 없거나 실패 → 기존 seeds 그대로

    expected_seg_count = int(duration_seconds / SEGMENT_LENGTH_SEC) + 1
    for seed in seeds:
        seed["audio_seed_backend"] = audio_backend
        seed["audio_profile_segment_count"] = expected_seg_count
        seed["audio_feature_backend"] = backend

    return seeds


def generate_audio_seeds(
    audio_path: Path | None,
    duration_seconds: float,
) -> list[dict]:
    """Audio-reaction track에서 WindowSeed 호환 dict 목록을 반환한다."""
    if audio_path is None:
        return []

    energy_profile = extract_audio_energy_profile(
        Path(audio_path), duration_seconds,
    )
    if not energy_profile:
        return []

    scored_segments = compute_audio_impact_scores(energy_profile)
    if not scored_segments:
        return []

    seeds: list[dict] = []
    seen: set[tuple[int, int]] = set()

    high_impact = [s for s in scored_segments if s["audio_impact"] >= 0.2]

    for anchor in high_impact:
        anchor_time = anchor["start"]
        for pre_pad in (3.0, 6.0, 10.0):
            for post_pad in (5.0, 10.0, 20.0):
                start_time = max(0.0, anchor_time - pre_pad)
                end_time = min(duration_seconds, anchor_time + anchor["end"] - anchor["start"] + post_pad)
                window_duration = end_time - start_time
                if window_duration < MIN_AUDIO_WINDOW_SEC or window_duration > MAX_AUDIO_WINDOW_SEC:
                    continue

                key = (int(round(start_time * 10)), int(round(end_time * 10)))
                if key in seen:
                    continue
                seen.add(key)

                window_segments = [
                    s for s in scored_segments
                    if s["start"] < end_time and s["end"] > start_time
                ]
                if not window_segments:
                    continue
                max_impact = max(s["audio_impact"] for s in window_segments)

                seeds.append({
                    "start_time": round(start_time, 3),
                    "end_time": round(end_time, 3),
                    "window_reason": "audio_reaction",
                    "candidate_track": "audio",
                    "audio_impact_score": round(max_impact, 3),
                    "anchor_time": round(anchor_time, 3),
                })

    seeds.sort(key=lambda s: s["audio_impact_score"], reverse=True)
    return seeds[:MAX_AUDIO_SEEDS]
