from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import candidates, episodes, exports, jobs, script_drafts, video_drafts

router = APIRouter()
router.include_router(episodes.router)
router.include_router(jobs.router)
router.include_router(candidates.router)
router.include_router(script_drafts.router)
router.include_router(video_drafts.router)
router.include_router(exports.router)
