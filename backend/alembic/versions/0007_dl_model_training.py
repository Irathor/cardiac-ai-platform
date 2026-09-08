"""Phase 8: DL model training (U-Net segmentation, CNN3D classification)

training_runs gains model_type so the worker knows which pipeline to run
(existing rows default to NEAREST_CENTROID, the only kind that existed
before). The two DL model types don't train against a DatasetVersion or
report a single scalar accuracy the way nearest-centroid does (see
docs/dl-training-runner.md and app.services.training_service), so the
columns that assumed exactly one training shape become nullable.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

from app.db.types import GUID

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_runs",
        sa.Column("model_type", sa.String(30), nullable=False, server_default="NEAREST_CENTROID"),
    )
    op.alter_column("training_runs", "dataset_version_id", existing_type=GUID(), nullable=True)
    op.alter_column("model_evaluations", "accuracy", existing_type=sa.Float(), nullable=True)
    op.alter_column("model_versions", "prototypes", existing_type=sa.JSON(), nullable=True)


def downgrade() -> None:
    op.alter_column("model_versions", "prototypes", existing_type=sa.JSON(), nullable=False)
    op.alter_column("model_evaluations", "accuracy", existing_type=sa.Float(), nullable=False)
    op.alter_column("training_runs", "dataset_version_id", existing_type=GUID(), nullable=False)
    op.drop_column("training_runs", "model_type")
