"""video_drafts and exports

Revision ID: 0002_video_drafts_exports
Revises: 0001_initial_schema
Create Date: 2026-03-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_video_drafts_exports"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "video_drafts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("candidate_id", sa.String(length=36), sa.ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("script_draft_id", sa.String(length=36), sa.ForeignKey("script_drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("template_type", sa.String(length=50), nullable=False),
        sa.Column("tts_voice_key", sa.String(length=100), nullable=True),
        sa.Column("aspect_ratio", sa.String(length=20), nullable=False, server_default="9:16"),
        sa.Column("width", sa.Integer(), nullable=False, server_default="1080"),
        sa.Column("height", sa.Integer(), nullable=False, server_default="1920"),
        sa.Column("draft_video_path", sa.Text(), nullable=True),
        sa.Column("subtitle_path", sa.Text(), nullable=True),
        sa.Column("waveform_path", sa.Text(), nullable=True),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column("burned_caption", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("render_config", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("timeline_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("operator_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_video_drafts_candidate_id", "video_drafts", ["candidate_id"])
    op.create_index("ix_video_drafts_script_draft_id", "video_drafts", ["script_draft_id"])

    op.create_table(
        "exports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("video_draft_id", sa.String(length=36), sa.ForeignKey("video_drafts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("export_video_path", sa.Text(), nullable=True),
        sa.Column("export_subtitle_path", sa.Text(), nullable=True),
        sa.Column("export_script_path", sa.Text(), nullable=True),
        sa.Column("export_metadata_path", sa.Text(), nullable=True),
        sa.Column("export_preset", sa.String(length=50), nullable=False, server_default="shorts_default"),
        sa.Column("file_size_bytes", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_exports_video_draft_id", "exports", ["video_draft_id"])


def downgrade() -> None:
    op.drop_index("ix_exports_video_draft_id", table_name="exports")
    op.drop_table("exports")
    op.drop_index("ix_video_drafts_script_draft_id", table_name="video_drafts")
    op.drop_index("ix_video_drafts_candidate_id", table_name="video_drafts")
    op.drop_table("video_drafts")
