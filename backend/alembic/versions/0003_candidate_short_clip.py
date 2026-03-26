"""candidate short_clip_path for ffmpeg shorts output

Revision ID: 0003_candidate_short_clip
Revises: 0002_video_drafts_exports
Create Date: 2026-03-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_candidate_short_clip"
down_revision = "0002_video_drafts_exports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("candidates", sa.Column("short_clip_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("candidates", "short_clip_path")
