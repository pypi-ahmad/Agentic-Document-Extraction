"""Add durable agentic page checkpoint metadata.

Revision ID: 0006_agentic_page_checkpoints
Revises: 0005_markdown_parser_reset
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_agentic_page_checkpoints"
down_revision: str | None = "0005_markdown_parser_reset"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("page_checkpoints", sa.Column("stage", sa.String(30)))
    op.add_column("page_checkpoints", sa.Column("observation_path", sa.String(1024)))
    op.add_column("page_checkpoints", sa.Column("plan_path", sa.String(1024)))
    op.add_column("page_checkpoints", sa.Column("diagnostics_path", sa.String(1024)))
    op.add_column("page_checkpoints", sa.Column("state_path", sa.String(1024)))
    op.add_column("page_checkpoints", sa.Column("fingerprint", sa.String(64)))
    op.add_column("page_checkpoints", sa.Column("quality_status", sa.String(20)))
    op.add_column("page_checkpoints", sa.Column("quality_score", sa.Float()))
    op.add_column(
        "page_checkpoints",
        sa.Column("repair_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    for name in (
        "repair_count",
        "quality_score",
        "quality_status",
        "fingerprint",
        "state_path",
        "diagnostics_path",
        "plan_path",
        "observation_path",
        "stage",
    ):
        op.drop_column("page_checkpoints", name)
