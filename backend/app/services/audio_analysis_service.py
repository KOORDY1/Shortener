"""고급 오디오 분석 서비스.

FFmpeg astats/ebur128 기반의 기본 RMS 측정을 넘어
librosa를 활용한 spectral 특징 추출을 제공한다.

설정:
  AUDIO_ANALYSIS_BACKEND=ffmpeg   # 기본, librosa 없어도 동작
  AUDIO_ANALYSIS_BACKEND=librosa  # librosa 설치 필요
  AUDIO_LIBROSA_ENABLED=false     # True면 librosa 강제 시도

librosa가 없으면 FFmpeg 기반으로 자동 폴백.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _extract_with_librosa(
    audio_path: Path,
    segment_length: float = 5.0,
    sample_rate: int = 16000,
) -> list[dict]:
    """librosa로 segment-level 오디오 특징을 추출한다.

    추출 특징:
    - rms: RMS 에너지
    - spectral_centroid: 음색 밝기 (높으면 흥분/긴장)
    - zcr: Zero-crossing rate (음성 vs 음악 구분)
    - mfcc_mean: MFCC 평균 13차원 (감정 분류 입력)

    Returns:
        list of segment dicts with start/end/rms/spectral_centroid/zcr/mfcc_mean
    """
    try:
        import librosa  # type: ignore[import-untyped]
        import numpy as np  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "librosa가 설치되지 않았습니다. "
            "`pip install librosa soundfile` 후 재시도하세요."
        ) from exc

    y, sr = librosa.load(str(audio_path), sr=sample_rate, mono=True)
    hop = int(segment_length * sr)
    segments: list[dict] = []

    for i, start_sample in enumerate(range(0, len(y), hop)):
        chunk: "np.ndarray[float, np.dtype[np.float32]]" = y[start_sample: start_sample + hop]
        if len(chunk) < sr:  # 1초 미만 스킵
            continue

        rms = float(np.sqrt(np.mean(chunk**2)))
        centroid = float(np.mean(librosa.feature.spectral_centroid(y=chunk, sr=sr)))
        zcr = float(np.mean(librosa.feature.zero_crossing_rate(chunk)))
        mfcc = librosa.feature.mfcc(y=chunk, sr=sr, n_mfcc=13)
        mfcc_mean: list[float] = [round(float(v), 4) for v in mfcc.mean(axis=1)]

        segments.append({
            "start": round(i * segment_length, 3),
            "end": round((i + 1) * segment_length, 3),
            "rms": round(rms, 4),
            "spectral_centroid": round(centroid, 1),
            "zcr": round(zcr, 4),
            "mfcc_mean": mfcc_mean,
            # rms_db 호환 필드 (기존 코드와 인터페이스 통일)
            "rms_db": round(
                20 * float(__import__("math").log10(max(rms, 1e-9))),
                1,
            ),
        })

    return segments


def extract_audio_features(
    audio_path: Path,
    *,
    segment_length: float = 5.0,
    backend: str = "auto",
) -> list[dict]:
    """오디오 특징 추출의 통합 인터페이스.

    Args:
        audio_path: 오디오 파일 경로
        segment_length: 분석 단위 (초)
        backend: "librosa" | "ffmpeg" | "auto"
            - "auto": librosa 시도, 없으면 ffmpeg 폴백
            - "librosa": librosa 강제 (없으면 ImportError)
            - "ffmpeg": ffmpeg ebur128 방식

    Returns:
        segment 딕셔너리 목록. 각 항목에 최소 start/end/rms_db 포함.
        librosa 백엔드는 추가로 spectral_centroid/zcr/mfcc_mean 포함.
    """
    if not audio_path.is_file():
        return []

    if backend == "librosa":
        return _extract_with_librosa(audio_path, segment_length=segment_length)

    if backend == "ffmpeg":
        from app.services.candidate_audio_signals import extract_audio_energy_profile_v2
        duration = _probe_duration(audio_path)
        return extract_audio_energy_profile_v2(audio_path, duration, segment_length)

    # auto: librosa 시도, 없으면 ffmpeg
    try:
        return _extract_with_librosa(audio_path, segment_length=segment_length)
    except ImportError:
        logger.debug("librosa 없음 — ffmpeg 폴백으로 오디오 분석")
        from app.services.candidate_audio_signals import extract_audio_energy_profile_v2
        duration = _probe_duration(audio_path)
        return extract_audio_energy_profile_v2(audio_path, duration, segment_length)


def _probe_duration(audio_path: Path) -> float:
    """ffprobe로 오디오 파일 길이를 초 단위로 반환한다."""
    import shutil
    import subprocess

    if not shutil.which("ffprobe"):
        return 9999.0
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return float(proc.stdout.strip()) if proc.stdout.strip() else 9999.0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 9999.0


def compute_audio_emotion_scores(segments: list[dict]) -> list[dict]:
    """librosa 특징에서 감정 점수를 계산한다.

    spectral_centroid와 zcr을 기반으로 간단한 감정 지표를 추가한다.
    librosa 특징이 없으면 (rms_db만 있는 경우) 원본 반환.

    추가 필드:
    - tension_hint: 고주파 성분 비율 (0~1) — 긴장감 지표
    - speech_likelihood: ZCR 기반 음성 vs 음악 구분 (0~1)
    """
    result: list[dict] = []
    if not segments:
        return result

    # spectral_centroid 없으면 ffmpeg 결과 — 추가 계산 없이 반환
    if "spectral_centroid" not in segments[0]:
        return list(segments)

    centroid_values = [float(s.get("spectral_centroid", 0.0)) for s in segments]
    max_centroid = max(centroid_values) if centroid_values else 1.0

    for seg in segments:
        centroid = float(seg.get("spectral_centroid", 0.0))
        zcr = float(seg.get("zcr", 0.0))

        tension_hint = min(1.0, centroid / max(max_centroid, 1.0))
        # ZCR > 0.1 → 음성(대사), ZCR < 0.05 → 악기/BGM
        speech_likelihood = min(1.0, max(0.0, (zcr - 0.05) / 0.15))

        result.append({
            **seg,
            "tension_hint": round(tension_hint, 3),
            "speech_likelihood": round(speech_likelihood, 3),
        })

    return result
