"""candidate_feedbacks.created_seq auto-increment column

Revision ID: 0006_feedback_created_seq
Revises: 0005_candidate_feedback
Create Date: 2026-04-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_feedback_created_seq"
down_revision = "0005_candidate_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "candidate_feedbacks" in set(inspector.get_table_names()):
        cols = {col["name"] for col in inspector.get_columns("candidate_feedbacks")}
        if "created_seq" not in cols:
            op.add_column(
                "candidate_feedbacks",
                sa.Column("created_seq", sa.Integer(), nullable=True, unique=True),
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "candidate_feedbacks" in set(inspector.get_table_names()):
        cols = {col["name"] for col in inspector.get_columns("candidate_feedbacks")}
        if "created_seq" in cols:
            op.drop_column("candidate_feedbacks", "created_seq")
