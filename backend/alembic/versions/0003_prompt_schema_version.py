"""prompt_version + schema_version on extractions.

Revision ID: 0003_prompt_schema_version
Revises: 0002_judgments
Create Date: 2026-06-22 04:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_prompt_schema_version"
down_revision: str | Sequence[str] | None = "0002_judgments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "extractions",
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "extractions",
        sa.Column("schema_version", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "ix_extractions_prompt_version",
        "extractions",
        ["prompt_version"],
    )
    op.create_index(
        "ix_extractions_schema_version",
        "extractions",
        ["schema_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_extractions_schema_version", table_name="extractions")
    op.drop_index("ix_extractions_prompt_version", table_name="extractions")
    op.drop_column("extractions", "schema_version")
    op.drop_column("extractions", "prompt_version")
