"""Phase 6: annotations, datasets, dataset_versions, dataset_cases

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

from app.db.types import GUID

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "annotations",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "based_on_segmentation_id", GUID(), sa.ForeignKey("segmentations.id"), nullable=False
        ),
        sa.Column("annotator_id", GUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("requested_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("corrected_segmentation_id", GUID(), sa.ForeignKey("segmentations.id"), nullable=True),
        sa.Column("diagnosis_label", sa.String(100), nullable=True),
        sa.Column("reviewer_id", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("review_comment", sa.String(2000), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_annotations_based_on_segmentation_id", "annotations", ["based_on_segmentation_id"])
    op.create_index("ix_annotations_annotator_id", "annotations", ["annotator_id"])
    op.create_index("ix_annotations_status", "annotations", ["status"])

    op.create_table(
        "datasets",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False, unique=True),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("created_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_datasets_name", "datasets", ["name"])

    op.create_table(
        "dataset_versions",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("dataset_id", GUID(), sa.ForeignKey("datasets.id"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="DRAFT"),
        sa.Column("checksum", sa.String(64), nullable=True),
        sa.Column("created_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dataset_id", "version_number", name="uq_dataset_version_number"),
    )
    op.create_index("ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"])

    op.create_table(
        "dataset_cases",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "dataset_version_id", GUID(), sa.ForeignKey("dataset_versions.id"), nullable=False
        ),
        sa.Column("patient_id", GUID(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("annotation_id", GUID(), sa.ForeignKey("annotations.id"), nullable=False),
        sa.Column("split", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("dataset_version_id", "annotation_id", name="uq_dataset_case_annotation"),
    )
    op.create_index("ix_dataset_cases_dataset_version_id", "dataset_cases", ["dataset_version_id"])
    op.create_index("ix_dataset_cases_patient_id", "dataset_cases", ["patient_id"])


def downgrade() -> None:
    op.drop_table("dataset_cases")
    op.drop_table("dataset_versions")
    op.drop_table("datasets")
    op.drop_table("annotations")
