"""Add durable automatic sub-document segmentation.

Revision ID: 0010_subdocuments
Revises: 0009_domain_profiles
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_subdocuments"
down_revision = "0009_domain_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "parse_jobs",
        sa.Column("segmentation_status", sa.String(30), nullable=False, server_default="not_run"),
    )
    op.create_table(
        "subdocuments",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("job_id", sa.String(32), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_page", sa.Integer(), nullable=False),
        sa.Column("end_page", sa.Integer(), nullable=False),
        sa.Column("profile", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("identifiers", sa.JSON(), nullable=False),
        sa.Column("boundary_confidence", sa.Float(), nullable=False),
        sa.Column("boundary_reasons", sa.JSON(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("missing_pages", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["parse_jobs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("job_id", "ordinal", name="uq_job_subdocument_ordinal"),
    )
    op.create_index("ix_subdocuments_job_id", "subdocuments", ["job_id"])
    with op.batch_alter_table("artifacts") as batch:
        batch.add_column(sa.Column("subdocument_id", sa.String(32), nullable=True))
        batch.create_foreign_key(
            "fk_artifacts_subdocument_id",
            "subdocuments",
            ["subdocument_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_index("ix_artifacts_subdocument_id", ["subdocument_id"])


def downgrade() -> None:
    with op.batch_alter_table("artifacts") as batch:
        batch.drop_index("ix_artifacts_subdocument_id")
        batch.drop_constraint("fk_artifacts_subdocument_id", type_="foreignkey")
        batch.drop_column("subdocument_id")
    op.drop_index("ix_subdocuments_job_id", table_name="subdocuments")
    op.drop_table("subdocuments")
    op.drop_column("parse_jobs", "segmentation_status")
