"""initial schema

Revision ID: 0001_initial_schema
Revises: None
Create Date: 2026-03-23 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "episodes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("show_title", sa.String(length=255), nullable=False),
        sa.Column("season_number", sa.Integer(), nullable=True),
        sa.Column("episode_number", sa.Integer(), nullable=True),
        sa.Column("episode_title", sa.String(length=255), nullable=True),
        sa.Column("original_language", sa.String(length=20), nullable=False),
        sa.Column("target_channel", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_video_path", sa.Text(), nullable=False),
        sa.Column("source_subtitle_path", sa.Text(), nullable=True),
        sa.Column("proxy_video_path", sa.Text(), nullable=True),
        sa.Column("audio_path", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("fps", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "shots",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(length=36),
            sa.ForeignKey("episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("shot_index", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(length=36),
            sa.ForeignKey("episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("segment_index", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("speaker_label", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "candidates",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(length=36),
            sa.ForeignKey("episodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("candidate_index", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("title_hint", sa.String(length=255), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=16), nullable=False),
        sa.Column("scores", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("risk_reasons", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "episode_id",
            sa.String(length=36),
            sa.ForeignKey("episodes.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_step", sa.String(length=128), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "script_drafts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.String(length=36),
            sa.ForeignKey("candidates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("hook_text", sa.Text(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("cta_text", sa.Text(), nullable=False),
        sa.Column("full_script_text", sa.Text(), nullable=False),
        sa.Column("estimated_duration_seconds", sa.Float(), nullable=False, server_default="0"),
        sa.Column("title_options", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("is_selected", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_index("ix_jobs_episode_id", "jobs", ["episode_id"])
    op.create_index("ix_jobs_candidate_id", "jobs", ["candidate_id"])
    op.create_index("ix_candidates_episode_id", "candidates", ["episode_id"])
    op.create_index("ix_script_drafts_candidate_id", "script_drafts", ["candidate_id"])


def downgrade() -> None:
    op.drop_index("ix_script_drafts_candidate_id", table_name="script_drafts")
    op.drop_index("ix_candidates_episode_id", table_name="candidates")
    op.drop_index("ix_jobs_candidate_id", table_name="jobs")
    op.drop_index("ix_jobs_episode_id", table_name="jobs")
    op.drop_table("script_drafts")
    op.drop_table("jobs")
    op.drop_table("candidates")
    op.drop_table("transcript_segments")
    op.drop_table("shots")
    op.drop_table("episodes")
