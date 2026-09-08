"""Imaging Phase 4: image_series, segmentations, biomarker_measurements

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

from app.db.types import GUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "image_series",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "imaging_study_id", GUID(), sa.ForeignKey("imaging_studies.id"), nullable=False
        ),
        sa.Column("series_type", sa.String(50), nullable=False, server_default="CINE_SHORT_AXIS"),
        sa.Column("phase", sa.String(20), nullable=True),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("voxel_spacing_x_mm", sa.Float(), nullable=False),
        sa.Column("voxel_spacing_y_mm", sa.Float(), nullable=False),
        sa.Column("voxel_spacing_z_mm", sa.Float(), nullable=False),
        sa.Column("shape_x", sa.Integer(), nullable=False),
        sa.Column("shape_y", sa.Integer(), nullable=False),
        sa.Column("shape_z", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_image_series_imaging_study_id", "image_series", ["imaging_study_id"])

    op.create_table(
        "segmentations",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("image_series_id", GUID(), sa.ForeignKey("image_series.id"), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("model_version", sa.String(200), nullable=True),
        sa.Column("created_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_segmentations_image_series_id", "segmentations", ["image_series_id"])

    op.create_table(
        "biomarker_measurements",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("segmentation_id", GUID(), sa.ForeignKey("segmentations.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_biomarker_measurements_segmentation_id", "biomarker_measurements", ["segmentation_id"]
    )
    op.create_index("ix_biomarker_measurements_name", "biomarker_measurements", ["name"])


def downgrade() -> None:
    op.drop_table("biomarker_measurements")
    op.drop_table("segmentations")
    op.drop_table("image_series")
