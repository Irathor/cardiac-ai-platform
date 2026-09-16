"""EPIC-4: MLflow Model Registry coordinates on model_versions

Adds mlflow_registry_name/mlflow_registry_version (NOT NULL — see ADR-2 and
EPIC-4's "Contrato técnico": after this change, every ModelVersion row is
only ever created *after* a successful mlflow.register_model call, so a row
without a Registry counterpart cannot exist going forward). Existing rows in
an environment with data are backfilled with mlflow_registry_name=name and
mlflow_registry_version='0' as a sentinel — see EPIC-4 point 3 — since those
rows predate this integration and never went through mlflow.register_model.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-16
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("model_versions", sa.Column("mlflow_registry_name", sa.String(200), nullable=True))
    op.add_column("model_versions", sa.Column("mlflow_registry_version", sa.String(20), nullable=True))

    model_versions = sa.table(
        "model_versions",
        sa.column("name", sa.String),
        sa.column("mlflow_registry_name", sa.String),
        sa.column("mlflow_registry_version", sa.String),
    )
    op.execute(
        model_versions.update().values(
            mlflow_registry_name=model_versions.c.name, mlflow_registry_version="0"
        )
    )

    with op.batch_alter_table("model_versions") as batch_op:
        batch_op.alter_column("mlflow_registry_name", existing_type=sa.String(200), nullable=False)
        batch_op.alter_column("mlflow_registry_version", existing_type=sa.String(20), nullable=False)


def downgrade() -> None:
    op.drop_column("model_versions", "mlflow_registry_version")
    op.drop_column("model_versions", "mlflow_registry_name")
