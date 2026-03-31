"""candidate failure_tags + candidate_feedbacks table

Revision ID: 0005_candidate_feedback
Revises: 0004_video_draft_metadata
Create Date: 2026-04-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_candidate_feedback"
down_revision = "0004_video_draft_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1) candidates.failure_tags 컬럼 추가
    candidate_cols = {col["name"] for col in inspector.get_columns("candidates")}
    if "failure_tags" not in candidate_cols:
        op.add_column(
            "candidates",
            sa.Column("failure_tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )

    # 2) candidate_feedbacks 테이블 생성
    existing_tables = set(inspector.get_table_names())
    if "candidate_feedbacks" not in existing_tables:
        op.create_table(
            "candidate_feedbacks",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "candidate_id",
                sa.String(36),
                sa.ForeignKey("candidates.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("action", sa.String(32), nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("failure_tags", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("before_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("after_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column("metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
        op.create_index(
            "ix_candidate_feedbacks_candidate_id",
            "candidate_feedbacks",
            ["candidate_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_tables = set(inspector.get_table_names())
    if "candidate_feedbacks" in existing_tables:
        op.drop_index("ix_candidate_feedbacks_candidate_id", table_name="candidate_feedbacks")
        op.drop_table("candidate_feedbacks")

    candidate_cols = {col["name"] for col in inspector.get_columns("candidates")}
    if "failure_tags" in candidate_cols:
        op.drop_column("candidates", "failure_tags")
