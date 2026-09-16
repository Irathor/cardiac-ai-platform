"""EPIC-3: Grad-CAM attribution storage on ai_analyses

Adds gradcam_storage_key (nullable — points at the .npy artifact in MinIO,
same pattern as Segmentation.storage_key) and gradcam_error (nullable —
honest reason when Grad-CAM itself failed but the classification succeeded;
see app.services.analysis_service.execute_analysis).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_analyses", sa.Column("gradcam_storage_key", sa.String(500), nullable=True))
    op.add_column("ai_analyses", sa.Column("gradcam_error", sa.String(2000), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_analyses", "gradcam_error")
    op.drop_column("ai_analyses", "gradcam_storage_key")
