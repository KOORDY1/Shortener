from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    candidate_actions,
    candidate_feedback,
    candidate_read,
    candidate_script_drafts,
    candidate_short_clip,
    candidate_subtitles,
    candidate_video_drafts,
)

router = APIRouter(tags=["candidates"])
router.include_router(candidate_read.router)
router.include_router(candidate_actions.router)
router.include_router(candidate_feedback.router)
router.include_router(candidate_script_drafts.router)
router.include_router(candidate_video_drafts.router)
router.include_router(candidate_subtitles.router)
router.include_router(candidate_short_clip.router)
