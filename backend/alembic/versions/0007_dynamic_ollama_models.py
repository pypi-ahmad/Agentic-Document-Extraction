"""Store per-job Ollama OCR and review model metadata.

Revision ID: 0007_dynamic_ollama_models
Revises: 0006_agentic_page_checkpoints
"""

import sqlalchemy as sa
from alembic import op

revision = "0007_dynamic_ollama_models"
down_revision = "0006_agentic_page_checkpoints"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parse_jobs", sa.Column("review_model_name", sa.String(120), nullable=True))
    op.add_column("parse_jobs", sa.Column("review_model_digest", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("parse_jobs", "review_model_digest")
    op.drop_column("parse_jobs", "review_model_name")
