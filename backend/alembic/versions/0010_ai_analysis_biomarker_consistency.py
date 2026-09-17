"""EPIC-12: biomarker consistency signal on ai_analyses

Adds biomarker_consistency (nullable JSON — the .as_dict() of
cardiac_ai_ml.classification.BiomarkerConsistency, an indirect consistency
signal between U-Net-derived biomarkers and the nearest-centroid
classifier's prototypes for the class a CNN3D analysis predicted) and
biomarker_consistency_error (nullable — honest reason when this signal
itself failed but the classification succeeded; see
app.services.analysis_service.execute_analysis). Own columns, not a reuse
of `features` (see EPIC-12's "Contrato técnico" section 4 for why).

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ai_analyses", sa.Column("biomarker_consistency", sa.JSON(), nullable=True))
    op.add_column("ai_analyses", sa.Column("biomarker_consistency_error", sa.String(2000), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_analyses", "biomarker_consistency_error")
    op.drop_column("ai_analyses", "biomarker_consistency")
