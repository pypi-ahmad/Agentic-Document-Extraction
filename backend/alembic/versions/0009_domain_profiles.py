"""Add detected document profile metadata.

Revision ID: 0009_domain_profiles
Revises: 0008_evaluation_runs
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_domain_profiles"
down_revision = "0008_evaluation_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parse_jobs", sa.Column("detected_profile", sa.String(40), nullable=True))
    op.add_column("parse_jobs", sa.Column("profile_confidence", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("parse_jobs", "profile_confidence")
    op.drop_column("parse_jobs", "detected_profile")
