"""ASR (Automatic Speech Recognition) 서비스.

openai-whisper 또는 faster-whisper로 오디오를 전사해
SubtitleCue 목록을 반환한다.
whisper 패키지가 없으면 ImportError를 발생시켜 호출 측이 graceful하게 처리할 수 있게 한다.

설정값:
  ASR_ENABLED=true
  WHISPER_MODEL_SIZE=medium   # tiny | base | small | medium | large
  DEFAULT_LANGUAGE=ko
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# SubtitleCue = (start_sec, end_sec, text) — subtitle_parse.py와 동일한 형식
SubtitleCue = tuple[float, float, str]


def _load_whisper_model(model_size: str):  # type: ignore[return]
    """openai-whisper 모델을 로드한다. 없으면 ImportError."""
    try:
        import whisper  # type: ignore[import-untyped]
        return whisper.load_model(model_size)
    except ImportError as exc:
        raise ImportError(
            "openai-whisper가 설치되지 않았습니다. "
            "`pip install openai-whisper` 후 재시도하세요."
        ) from exc


def transcribe_with_whisper(
    audio_path: Path,
    *,
    model_size: str = "medium",
    language: str = "ko",
    initial_prompt: str = "",
) -> list[SubtitleCue]:
    """Whisper로 오디오를 전사해 SubtitleCue 목록을 반환한다.

    Args:
        audio_path: 전사할 오디오 파일 경로 (mp3/m4a/wav 등)
        model_size: Whisper 모델 크기 (tiny/base/small/medium/large)
        language: 언어 코드 (예: "ko", "en")
        initial_prompt: 도메인 힌트 (예: "드라마 대사, 한국어")

    Returns:
        list of (start_sec, end_sec, text) tuples

    Raises:
        ImportError: openai-whisper가 설치되지 않은 경우
        FileNotFoundError: 오디오 파일이 없는 경우
    """
    if not audio_path.is_file():
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {audio_path}")

    model = _load_whisper_model(model_size)
    result = model.transcribe(
        str(audio_path),
        language=language,
        initial_prompt=initial_prompt or "드라마 대사" if language == "ko" else "",
        word_timestamps=True,
        condition_on_previous_text=False,
        compression_ratio_threshold=2.2,
        no_speech_threshold=0.6,
    )

    cues: list[SubtitleCue] = []
    for seg in result.get("segments") or []:
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", 0.0))
        text = str(seg.get("text", "")).strip()
        if end > start and text:
            cues.append((round(start, 3), round(end, 3), text))

    return cues


def transcribe_with_faster_whisper(
    audio_path: Path,
    *,
    model_size: str = "medium",
    language: str = "ko",
    initial_prompt: str = "",
) -> list[SubtitleCue]:
    """faster-whisper로 오디오를 전사한다 (openai-whisper 대비 2~4× 빠름).

    Args:
        audio_path: 전사할 오디오 파일 경로
        model_size: 모델 크기 (tiny/base/small/medium/large)
        language: 언어 코드
        initial_prompt: 도메인 힌트

    Returns:
        list of (start_sec, end_sec, text) tuples

    Raises:
        ImportError: faster-whisper가 설치되지 않은 경우
        FileNotFoundError: 오디오 파일이 없는 경우
    """
    if not audio_path.is_file():
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {audio_path}")

    try:
        from faster_whisper import WhisperModel  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "faster-whisper가 설치되지 않았습니다. "
            "`pip install faster-whisper` 후 재시도하세요."
        ) from exc

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(audio_path),
        language=language,
        initial_prompt=initial_prompt or ("드라마 대사" if language == "ko" else ""),
        condition_on_previous_text=False,
        compression_ratio_threshold=2.2,
        no_speech_threshold=0.6,
    )

    cues: list[SubtitleCue] = []
    for seg in segments:
        text = str(seg.text).strip()
        if seg.end > seg.start and text:
            cues.append((round(seg.start, 3), round(seg.end, 3), text))

    return cues


def transcribe_audio(
    audio_path: Path,
    *,
    model_size: str = "medium",
    language: str = "ko",
    initial_prompt: str = "",
    prefer_faster_whisper: bool = True,
) -> list[SubtitleCue]:
    """faster-whisper 우선, 없으면 openai-whisper로 폴백해 전사한다.

    Returns:
        list of (start_sec, end_sec, text) tuples. 둘 다 없으면 빈 목록.
    """
    if prefer_faster_whisper:
        try:
            return transcribe_with_faster_whisper(
                audio_path,
                model_size=model_size,
                language=language,
                initial_prompt=initial_prompt,
            )
        except ImportError:
            pass

    try:
        return transcribe_with_whisper(
            audio_path,
            model_size=model_size,
            language=language,
            initial_prompt=initial_prompt,
        )
    except ImportError:
        return []
