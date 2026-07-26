"""Add quality policy snapshots and curated review records.

Revision ID: 0012_quality_feedback
Revises: 0011_extraction_schemas
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_quality_feedback"
down_revision = "0011_extraction_schemas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("parse_jobs") as batch:
        batch.add_column(sa.Column("quality_policy_snapshot", sa.JSON(), nullable=True))
    op.create_table(
        "review_cases",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(32),
            sa.ForeignKey("parse_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_kind", sa.String(40), nullable=False),
        sa.Column("item_key", sa.String(255), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("failure_codes", sa.JSON(), nullable=False),
        sa.Column("original", sa.JSON(), nullable=False),
        sa.Column("current", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False, unique=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_review_cases_job_status", "review_cases", ["job_id", "status"])
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "case_id",
            sa.String(32),
            sa.ForeignKey("review_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("corrected", sa.JSON(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reviewer", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("case_id", "revision", name="uq_review_decision_revision"),
    )
    op.create_table(
        "curated_documents",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(32),
            sa.ForeignKey("parse_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("label_path", sa.String(1024), nullable=False),
        sa.Column("label_sha256", sa.String(64), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "curated_exports",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("document_ids", sa.JSON(), nullable=False),
        sa.Column("archive_path", sa.String(1024), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("name", "version", name="uq_curated_export_version"),
    )


def downgrade() -> None:
    op.drop_table("curated_exports")
    op.drop_table("curated_documents")
    op.drop_table("review_decisions")
    op.drop_index("ix_review_cases_job_status", table_name="review_cases")
    op.drop_table("review_cases")
    with op.batch_alter_table("parse_jobs") as batch:
        batch.drop_column("quality_policy_snapshot")
