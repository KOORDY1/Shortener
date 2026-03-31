from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = BASE_DIR / "data"
DEFAULT_STORAGE_DIR = BASE_DIR / "storage"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Drama Shorts Copilot API"
    api_v1_prefix: str = "/api/v1"
    database_url: str = f"sqlite:///{(DEFAULT_DATA_DIR / 'app.db').as_posix()}"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "memory://"
    celery_result_backend: str = "cache+memory://"
    celery_task_always_eager: bool = True
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1"
    allow_mock_llm_fallback: bool = True
    # true이면 분석 파이프라인에서 후보 목록을 OpenAI로 재조정(자막 발췌만 전달, 영상 바이너리 없음)
    candidate_rerank_llm: bool = False
    # 멀티모달 후보 재랭크(프레임+자막)를 켭니다. legacy CANDIDATE_RERANK_LLM=true 도 허용합니다.
    vision_candidate_rerank: bool = True
    vision_max_candidates_per_episode: int = 8
    vision_max_frames_per_candidate: int = 6
    vision_image_max_width: int = 640
    vision_model: str = "gpt-4.1"
    vision_prompt_version: str = "vision_candidate_rerank_v2"
    vision_scan_version: str = "vision_scan_v1"
    analysis_pipeline_version: str = "analysis_pipeline_v2"
    proxy_transcode_version: str = "proxy_v2"
    proxy_max_width: int = 480
    proxy_video_fps: int = 6
    proxy_video_crf: int = 31
    proxy_audio_bitrate_kbps: int = 64
    # FFmpeg select(scene) 임계값 (낮을수록 컷이 많이 잡힘)
    ffmpeg_scene_threshold: float = 0.32
    # ASR (Whisper)
    asr_enabled: bool = False
    whisper_model_size: str = "medium"   # tiny | base | small | medium | large
    whisper_prefer_faster: bool = True   # faster-whisper 우선, 없으면 openai-whisper
    default_language: str = "ko"

    # 오디오 분석 백엔드
    audio_analysis_backend: str = "ffmpeg"  # "ffmpeg" | "librosa" | "auto"
    audio_librosa_enabled: bool = False

    # ML 임베딩 언어 시그널 (기본 비활성 — OPENAI_API_KEY 필요)
    embedding_signals_enabled: bool = False
    embedding_signals_model: str = "text-embedding-3-small"
    embedding_signals_max_chars: int = 1000

    # LLM Arc Judge
    llm_arc_judge_enabled: bool = False
    llm_arc_judge_top_k: int = 5
    llm_arc_judge_model: str = "gpt-4.1-mini"

    # 스코어링 프로파일 (A/B 테스트용)
    scoring_profile: str = "default"  # "default" | "reaction_heavy" | "payoff_heavy"

    # 길이 정책 (search window / core span / render target)
    length_min_window_sec: float = 30.0
    length_max_window_sec: float = 180.0
    length_max_2span_sec: float = 64.0
    length_max_3span_sec: float = 90.0
    length_render_target_min_sec: float = 30.0
    length_render_target_max_sec: float = 75.0
    length_render_ideal_sec: float = 50.0

    storage_root: str = str(DEFAULT_STORAGE_DIR)
    # 브라우저에서 Next.js(dev)가 별도 포트로 API를 호출할 때 필요. 콤마로 구분.
    cors_allowed_origins: str = (
        "http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001"
    )

    @property
    def resolved_storage_root(self) -> Path:
        path = Path(self.storage_root)
        if path.is_absolute():
            return path
        return (BASE_DIR / path).resolve()

    @property
    def resolved_data_root(self) -> Path:
        return DEFAULT_DATA_DIR.resolve()

    @property
    def vision_rerank_enabled(self) -> bool:
        return bool(self.vision_candidate_rerank or self.candidate_rerank_llm)


@lru_cache
def get_settings() -> Settings:
    return Settings()
