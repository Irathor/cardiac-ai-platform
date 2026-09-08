"""Phase 7: training_runs, model_versions, model_evaluations, model_approvals

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

from app.db.types import GUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "training_runs",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("dataset_version_id", GUID(), sa.ForeignKey("dataset_versions.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("mlflow_run_id", sa.String(100), nullable=True),
        sa.Column("requested_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(2000), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_training_runs_dataset_version_id", "training_runs", ["dataset_version_id"])
    op.create_index("ix_training_runs_status", "training_runs", ["status"])

    op.create_table(
        "model_versions",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("training_run_id", GUID(), sa.ForeignKey("training_runs.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("mlflow_run_id", sa.String(100), nullable=False),
        sa.Column("mlflow_model_uri", sa.String(500), nullable=False),
        sa.Column("prototypes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING_REVIEW"),
        sa.Column("created_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_versions_training_run_id", "model_versions", ["training_run_id"])
    op.create_index("ix_model_versions_name", "model_versions", ["name"])
    op.create_index("ix_model_versions_status", "model_versions", ["status"])

    op.create_table(
        "model_evaluations",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("model_version_id", GUID(), sa.ForeignKey("model_versions.id"), nullable=False),
        sa.Column("split", sa.String(20), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_evaluations_model_version_id", "model_evaluations", ["model_version_id"])

    op.create_table(
        "model_approvals",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("model_version_id", GUID(), sa.ForeignKey("model_versions.id"), nullable=False),
        sa.Column("approver_id", GUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("justification", sa.String(2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_model_approvals_model_version_id", "model_approvals", ["model_version_id"])


def downgrade() -> None:
    op.drop_table("model_approvals")
    op.drop_table("model_evaluations")
    op.drop_table("model_versions")
    op.drop_table("training_runs")
