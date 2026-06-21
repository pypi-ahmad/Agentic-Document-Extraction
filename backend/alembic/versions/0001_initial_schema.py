"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-22 00:00:00

Initial schema for the v0.3.0 release.

Six tables:
  - documents
  - extraction_schemas
  - extractions
  - extraction_steps
  - extraction_reviews
  - extraction_audit_log

This migration matches the schema that ``Base.metadata.create_all``
would have produced in v0.2.x. Users upgrading from v0.2.x should run
``alembic stamp head`` against their existing ``extraction.db`` instead
of letting this migration run, so they keep their data.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("file_type", sa.String(length=20), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="uploaded"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    op.create_table(
        "extraction_schemas",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    op.create_table(
        "extractions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(length=32),
            sa.ForeignKey("documents.id"),
            nullable=False,
        ),
        sa.Column(
            "schema_id",
            sa.String(length=32),
            sa.ForeignKey("extraction_schemas.id"),
            nullable=False,
        ),
        sa.Column("ocr_provider", sa.String(length=50), server_default="auto"),
        sa.Column("llm_provider", sa.String(length=50), server_default="auto"),
        sa.Column("llm_model", sa.String(length=100), server_default="auto"),
        sa.Column("status", sa.String(length=30), server_default="pending"),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("validation_errors", sa.JSON(), nullable=True),
        sa.Column("validation_results", sa.JSON(), nullable=True),
        sa.Column("review_verdict", sa.String(length=20), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("ocr_provider_used", sa.String(length=50), nullable=True),
        sa.Column("llm_provider_used", sa.String(length=50), nullable=True),
        sa.Column("llm_model_used", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.JSON(), nullable=True),
        sa.Column("extract_attempts", sa.Integer(), nullable=True),
        sa.Column("error_category", sa.String(length=30), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "extraction_steps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "extraction_id",
            sa.String(length=32),
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )

    op.create_table(
        "extraction_reviews",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "extraction_id",
            sa.String(length=32),
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("corrected_fields", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )

    op.create_table(
        "extraction_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "extraction_id",
            sa.String(length=32),
            sa.ForeignKey("extractions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=128), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_extraction_audit_log_extraction_id",
        "extraction_audit_log",
        ["extraction_id"],
    )
    op.create_index(
        "ix_extraction_audit_log_event",
        "extraction_audit_log",
        ["event"],
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_audit_log_event", table_name="extraction_audit_log")
    op.drop_index("ix_extraction_audit_log_extraction_id", table_name="extraction_audit_log")
    op.drop_table("extraction_audit_log")
    op.drop_table("extraction_reviews")
    op.drop_table("extraction_steps")
    op.drop_table("extractions")
    op.drop_table("extraction_schemas")
    op.drop_table("documents")
