"""extraction_judgments table for G-Eval LLM-as-judge scores.

Revision ID: 0002_judgments
Revises: 0001_initial
Create Date: 2026-06-22 03:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_judgments"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "extraction_judgments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "extraction_id",
            sa.String(length=32),
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("judge_model", sa.String(length=100), nullable=False),
        sa.Column(
            "judge_version",
            sa.String(length=20),
            nullable=False,
            server_default="geval-1",
        ),
        sa.Column("scores", sa.JSON(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_extraction_judgments_extraction_id",
        "extraction_judgments",
        ["extraction_id"],
    )
    op.create_index(
        "ix_extraction_judgments_overall_score",
        "extraction_judgments",
        ["overall_score"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_extraction_judgments_overall_score", table_name="extraction_judgments"
    )
    op.drop_index(
        "ix_extraction_judgments_extraction_id", table_name="extraction_judgments"
    )
    op.drop_table("extraction_judgments")
