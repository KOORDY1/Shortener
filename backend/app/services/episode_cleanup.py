from __future__ import annotations

import shutil

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Candidate, Episode, EpisodeStatus, Job, Shot, TranscriptSegment
from app.services.storage_service import episode_root


def delete_episode_storage(episode_id: str) -> None:
    """에피소드 스토리지 디렉터리 전체 삭제(원본 포함)."""
    if not episode_id or "/" in episode_id or ".." in episode_id:
        return
    settings = get_settings()
    root = (settings.resolved_storage_root / "episodes" / episode_id).resolve()
    base = (settings.resolved_storage_root / "episodes").resolve()
    try:
        root.relative_to(base)
    except ValueError:
        return
    if root.is_dir():
        shutil.rmtree(root, ignore_errors=True)


def delete_derived_episode_storage(episode_id: str, *, preserve_cache: bool = False) -> None:
    """원본(source/)은 두고 분석·렌더 산출물만 삭제."""
    root = episode_root(episode_id)
    if not root.is_dir():
        return
    preserved_names = {"source"}
    if preserve_cache:
        preserved_names.update({"proxy", "audio", "shots", "cache"})
    for child in root.iterdir():
        if child.name in preserved_names:
            continue
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except OSError:
                pass


def delete_episode_cache_storage(episode_id: str) -> None:
    """분석 가속용 캐시(proxy/audio/shots/cache)만 삭제."""
    root = episode_root(episode_id)
    if not root.is_dir():
        return
    for name in ("proxy", "audio", "shots", "cache"):
        child = root / name
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        elif child.exists():
            try:
                child.unlink()
            except OSError:
                pass


def clear_episode_analysis(db: Session, episode_id: str) -> Episode:
    """DB에서 샷·대본·후보·관련 작업을 지우고 에피소드를 업로드 직후 상태로 되돌립니다."""
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise ValueError("Episode not found")

    db.execute(delete(Job).where(Job.episode_id == episode_id))
    db.execute(delete(Candidate).where(Candidate.episode_id == episode_id))
    db.execute(delete(Shot).where(Shot.episode_id == episode_id))
    db.execute(delete(TranscriptSegment).where(TranscriptSegment.episode_id == episode_id))

    episode.status = EpisodeStatus.UPLOADED.value
    md = dict(episode.metadata_json or {})
    md.pop("signals", None)
    md.pop("vision_rerank", None)
    md.pop("analysis_pipeline", None)
    md.pop("transcript_source", None)
    md.pop("transcript_error", None)
    md.pop("transcript_note", None)
    episode.metadata_json = md
    db.add(episode)
    db.commit()
    db.refresh(episode)

    delete_derived_episode_storage(episode_id, preserve_cache=True)
    return episode


def clear_episode_cache(db: Session, episode_id: str) -> Episode:
    """분석 가속용 캐시만 지웁니다. 후보/대본 같은 DB 결과는 유지합니다."""
    episode = db.get(Episode, episode_id)
    if episode is None:
        raise ValueError("Episode not found")

    db.execute(delete(Shot).where(Shot.episode_id == episode_id))

    episode.proxy_video_path = None
    episode.audio_path = None
    md = dict(episode.metadata_json or {})
    md.pop("proxy_transcode", None)
    md.pop("shot_detection", None)
    md.pop("vision_scan", None)
    md.pop("vision_rerank", None)
    md.pop("analysis_pipeline", None)
    episode.metadata_json = md
    db.add(episode)
    db.commit()
    db.refresh(episode)

    delete_episode_cache_storage(episode_id)
    return episode
