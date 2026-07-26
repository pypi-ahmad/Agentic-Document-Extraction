"""Add persistent batches, output revisions, and reprocessing audit runs.

Revision ID: 0013_inspection_batches
Revises: 0012_quality_feedback
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_inspection_batches"
down_revision = "0012_quality_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parse_batches",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="queued"),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("bundle_path", sa.String(1024), nullable=True),
        sa.Column("bundle_sha256", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_parse_batches_status", "parse_batches", ["status"])
    with op.batch_alter_table("parse_jobs") as batch:
        batch.add_column(sa.Column("batch_id", sa.String(32), nullable=True))
        batch.add_column(sa.Column("batch_ordinal", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("output_revision", sa.Integer(), nullable=False, server_default="1")
        )
        batch.create_foreign_key(
            "fk_parse_jobs_batch_id", "parse_batches", ["batch_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_index("ix_parse_jobs_batch_id", ["batch_id"])
    op.create_table(
        "reprocess_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(32),
            sa.ForeignKey("parse_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_kind", sa.String(20), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("region_id", sa.String(40), nullable=True),
        sa.Column("dpi", sa.Integer(), nullable=False),
        sa.Column("crop_padding", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("previous_fingerprint", sa.String(64), nullable=True),
        sa.Column("result_fingerprint", sa.String(64), nullable=True),
        sa.Column("decision", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_reprocess_runs_job_id", "reprocess_runs", ["job_id"])
    op.create_index("ix_reprocess_runs_status", "reprocess_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_reprocess_runs_status", table_name="reprocess_runs")
    op.drop_index("ix_reprocess_runs_job_id", table_name="reprocess_runs")
    op.drop_table("reprocess_runs")
    with op.batch_alter_table("parse_jobs") as batch:
        batch.drop_index("ix_parse_jobs_batch_id")
        batch.drop_constraint("fk_parse_jobs_batch_id", type_="foreignkey")
        batch.drop_column("output_revision")
        batch.drop_column("batch_ordinal")
        batch.drop_column("batch_id")
    op.drop_index("ix_parse_batches_status", table_name="parse_batches")
    op.drop_table("parse_batches")
