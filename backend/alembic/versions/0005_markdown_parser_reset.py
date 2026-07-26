"""Replace extraction schema with durable Markdown parse jobs.

Revision ID: 0005_markdown_parser_reset
Revises: 0004_evidence_entities_verifier
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_markdown_parser_reset"
down_revision: str | None = "0004_evidence_entities_verifier"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_TABLES = [
    "extraction_verifier_runs",
    "extraction_entities",
    "extraction_evidence",
    "extraction_audit_log",
    "extraction_judgments",
    "extraction_reviews",
    "extraction_steps",
    "extractions",
    "extraction_schemas",
    "documents",
]


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    for table in LEGACY_TABLES:
        if table in existing:
            op.drop_table(table)

    op.create_table(
        "parse_jobs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("source_path", sa.String(1024), nullable=False),
        sa.Column("source_mime", sa.String(100), nullable=False),
        sa.Column("source_size", sa.Integer(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(40), nullable=False, server_default="queued"),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("current_page", sa.Integer()),
        sa.Column("completed_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warning_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text()),
        sa.Column("model_name", sa.String(120)),
        sa.Column("model_digest", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_parse_jobs_source_sha256", "parse_jobs", ["source_sha256"])
    op.create_index("ix_parse_jobs_status", "parse_jobs", ["status"])

    op.create_table(
        "page_checkpoints",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("job_id", sa.String(32), sa.ForeignKey("parse_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("routing", sa.String(40)),
        sa.Column("layout_path", sa.String(1024)),
        sa.Column("layout_sha256", sa.String(64)),
        sa.Column("warnings", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("error_code", sa.String(80)),
        sa.Column("error_message", sa.Text()),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Float()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("job_id", "page_number", name="uq_job_page"),
    )
    op.create_index("ix_page_checkpoints_job_id", "page_checkpoints", ["job_id"])
    op.create_index("ix_page_checkpoints_status", "page_checkpoints", ["status"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("job_id", sa.String(32), sa.ForeignKey("parse_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("region_id", sa.String(40)),
        sa.Column("relative_path", sa.String(1024), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("job_id", "type", "region_id", name="uq_job_artifact"),
    )
    op.create_index("ix_artifacts_job_id", "artifacts", ["job_id"])


def downgrade() -> None:
    op.drop_table("artifacts")
    op.drop_table("page_checkpoints")
    op.drop_table("parse_jobs")
