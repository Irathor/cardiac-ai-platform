"""Inference Phase 5: ai_analyses

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

from app.db.types import GUID

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_analyses",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "imaging_study_id", GUID(), sa.ForeignKey("imaging_studies.id"), nullable=False
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("model_version", sa.String(200), nullable=False),
        sa.Column("features", sa.JSON(), nullable=True),
        sa.Column("predicted_class", sa.String(100), nullable=True),
        sa.Column("probabilities", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("feature_attributions", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("requested_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_analyses_imaging_study_id", "ai_analyses", ["imaging_study_id"])
    op.create_index("ix_ai_analyses_status", "ai_analyses", ["status"])


def downgrade() -> None:
    op.drop_table("ai_analyses")
