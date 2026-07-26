"""Add durable lease-based page tasks for the OpenAI V2 pipeline.

Revision ID: 0014_openai_v2_page_tasks
Revises: 0013_inspection_batches
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_openai_v2_page_tasks"
down_revision = "0013_inspection_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v2_page_tasks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "job_id",
            sa.String(32),
            sa.ForeignKey("parse_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_owner", sa.String(120), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result_path", sa.String(1024), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("job_id", "page_number", name="uq_v2_job_page_task"),
    )
    op.create_index("ix_v2_page_tasks_job_id", "v2_page_tasks", ["job_id"])
    op.create_index("ix_v2_page_tasks_status", "v2_page_tasks", ["status"])
    op.create_index("ix_v2_page_tasks_lease_owner", "v2_page_tasks", ["lease_owner"])
    op.create_index(
        "ix_v2_page_tasks_lease_expires_at", "v2_page_tasks", ["lease_expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_v2_page_tasks_lease_expires_at", table_name="v2_page_tasks")
    op.drop_index("ix_v2_page_tasks_lease_owner", table_name="v2_page_tasks")
    op.drop_index("ix_v2_page_tasks_status", table_name="v2_page_tasks")
    op.drop_index("ix_v2_page_tasks_job_id", table_name="v2_page_tasks")
    op.drop_table("v2_page_tasks")
