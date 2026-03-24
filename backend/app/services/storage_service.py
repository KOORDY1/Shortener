from __future__ import annotations

from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings


settings = get_settings()


def ensure_storage_layout() -> None:
    settings.resolved_storage_root.mkdir(parents=True, exist_ok=True)
    settings.resolved_data_root.mkdir(parents=True, exist_ok=True)


def episode_root(episode_id: str) -> Path:
    path = settings.resolved_storage_root / "episodes" / episode_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_upload(episode_id: str, upload: UploadFile, subdir: str, filename: str) -> str:
    target_dir = episode_root(episode_id) / subdir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / filename
    with target_path.open("wb") as buffer:
        while chunk := upload.file.read(1024 * 1024):
            buffer.write(chunk)
    return str(target_path)


def write_placeholder(episode_id: str, relative_parts: list[str], content: str) -> str:
    target_path = episode_root(episode_id).joinpath(*relative_parts)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(content, encoding="utf-8")
    return str(target_path)
