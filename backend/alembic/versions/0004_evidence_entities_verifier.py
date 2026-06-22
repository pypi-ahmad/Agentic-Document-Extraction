"""v0.5.0 evidence, entities, and verifier tables.

Adds three new tables that back the v0.5.0 multi-modal,
evidence-grounded pipeline:

* ``extraction_evidence`` — one row per field with page, bbox,
  text_span, and evidence_score. Backed by
  ``app.services.extraction.evidence``.
* ``extraction_entities`` — cross-page entity mentions, one row
  per canonical entity. Backed by
  ``app.services.extraction.cross_page``.
* ``extraction_verifier_runs`` — one row per verifier run with
  per-field verdicts and a list of disputed fields. Backed by
  ``app.services.extraction.verifier``.

Revision ID: 0004_evidence_entities_verifier
Revises: 0003_prompt_schema_version
Create Date: 2026-06-22 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_evidence_entities_verifier"
down_revision: str | Sequence[str] | None = "0003_prompt_schema_version"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "extraction_evidence",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "extraction_id",
            sa.String(length=32),
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("field", sa.String(length=100), nullable=False),
        sa.Column("value", sa.JSON(), nullable=True),
        sa.Column("page", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("bbox_json", sa.JSON(), nullable=True),
        sa.Column("text_span", sa.Text(), nullable=False, server_default=""),
        sa.Column("source_region_id", sa.String(length=64), nullable=True),
        sa.Column("evidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("prompt_version", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_extraction_evidence_extraction_id",
        "extraction_evidence",
        ["extraction_id"],
    )
    op.create_index(
        "ix_extraction_evidence_field",
        "extraction_evidence",
        ["field"],
    )

    op.create_table(
        "extraction_entities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "extraction_id",
            sa.String(length=32),
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=40), nullable=False, server_default="generic"),
        sa.Column("canonical_form", sa.String(length=255), nullable=False),
        sa.Column("mentions", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_extraction_entities_extraction_id",
        "extraction_entities",
        ["extraction_id"],
    )

    op.create_table(
        "extraction_verifier_runs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "extraction_id",
            sa.String(length=32),
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("verifier_model", sa.String(length=100), nullable=False),
        sa.Column(
            "verifier_version",
            sa.String(length=20),
            nullable=False,
            server_default="verifier-1",
        ),
        sa.Column("field_verdicts", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("disputed_fields", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("overall_agreement", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_extraction_verifier_runs_extraction_id",
        "extraction_verifier_runs",
        ["extraction_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_extraction_verifier_runs_extraction_id", table_name="extraction_verifier_runs"
    )
    op.drop_table("extraction_verifier_runs")

    op.drop_index("ix_extraction_entities_extraction_id", table_name="extraction_entities")
    op.drop_table("extraction_entities")

    op.drop_index("ix_extraction_evidence_field", table_name="extraction_evidence")
    op.drop_index("ix_extraction_evidence_extraction_id", table_name="extraction_evidence")
    op.drop_table("extraction_evidence")
