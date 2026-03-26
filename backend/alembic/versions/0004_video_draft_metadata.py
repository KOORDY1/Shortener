"""video_drafts metadata json

Revision ID: 0004_video_draft_metadata
Revises: 0003_candidate_short_clip
Create Date: 2026-03-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_video_draft_metadata"
down_revision = "0003_candidate_short_clip"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("video_drafts")}
    if "metadata" not in columns:
        op.add_column(
            "video_drafts",
            sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("video_drafts")}
    if "metadata" in columns:
        op.drop_column("video_drafts", "metadata")
