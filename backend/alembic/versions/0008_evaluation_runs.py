"""Add durable grounded-document evaluation runs.

Revision ID: 0008_evaluation_runs
Revises: 0007_dynamic_ollama_models
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_evaluation_runs"
down_revision = "0007_dynamic_ollama_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("report_path", sa.String(1024), nullable=True),
        sa.Column("total_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_cases", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_evaluation_runs_status", "evaluation_runs", ["status"])
    op.create_table(
        "evaluation_cases",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("run_id", sa.String(32), sa.ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(200), nullable=False),
        sa.Column("parse_job_id", sa.String(32), sa.ForeignKey("parse_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("gold_path", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("report_path", sa.String(1024), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", "external_id", name="uq_evaluation_case_external"),
    )
    op.create_index("ix_evaluation_cases_run_id", "evaluation_cases", ["run_id"])
    op.create_index("ix_evaluation_cases_parse_job_id", "evaluation_cases", ["parse_job_id"])
    op.create_index("ix_evaluation_cases_status", "evaluation_cases", ["status"])


def downgrade() -> None:
    op.drop_table("evaluation_cases")
    op.drop_table("evaluation_runs")
