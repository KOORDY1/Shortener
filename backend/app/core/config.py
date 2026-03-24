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
    openai_model: str = "gpt-4.1-mini"
    allow_mock_llm_fallback: bool = True
    storage_root: str = str(DEFAULT_STORAGE_DIR)

    @property
    def resolved_storage_root(self) -> Path:
        path = Path(self.storage_root)
        if path.is_absolute():
            return path
        return (BASE_DIR / path).resolve()

    @property
    def resolved_data_root(self) -> Path:
        return DEFAULT_DATA_DIR.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
