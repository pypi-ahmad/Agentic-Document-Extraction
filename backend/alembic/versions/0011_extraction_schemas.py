"""Add reusable grounded extraction schemas.

Revision ID: 0011_extraction_schemas
Revises: 0010_subdocuments
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_extraction_schemas"
down_revision = "0010_subdocuments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extraction_schemas",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_key", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("schema_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    with op.batch_alter_table("parse_jobs") as batch:
        batch.add_column(sa.Column("extraction_schema_id", sa.String(32), nullable=True))
        batch.add_column(sa.Column("extraction_schema_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("extraction_model_name", sa.String(120), nullable=True))
        batch.add_column(sa.Column("extraction_model_digest", sa.String(128), nullable=True))
        batch.create_foreign_key(
            "fk_parse_jobs_extraction_schema_id",
            "extraction_schemas",
            ["extraction_schema_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_parse_jobs_extraction_schema_id", ["extraction_schema_id"])


def downgrade() -> None:
    with op.batch_alter_table("parse_jobs") as batch:
        batch.drop_index("ix_parse_jobs_extraction_schema_id")
        batch.drop_constraint("fk_parse_jobs_extraction_schema_id", type_="foreignkey")
        batch.drop_column("extraction_model_digest")
        batch.drop_column("extraction_model_name")
        batch.drop_column("extraction_schema_snapshot")
        batch.drop_column("extraction_schema_id")
    op.drop_table("extraction_schemas")
