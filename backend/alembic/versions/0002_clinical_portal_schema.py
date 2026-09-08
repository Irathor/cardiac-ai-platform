"""Clinical portal: patients, doctor assignments, imaging studies, clinical reviews

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-08
"""
import sqlalchemy as sa
from alembic import op

from app.db.types import GUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "patients",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("organization_id", GUID(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("identifier", sa.String(50), nullable=False, unique=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("date_of_birth", sa.Date(), nullable=False),
        sa.Column("sex", sa.String(20), nullable=True),
        sa.Column("height_cm", sa.Float(), nullable=True),
        sa.Column("weight_kg", sa.Float(), nullable=True),
        sa.Column("registered_diagnosis", sa.String(100), nullable=True),
        sa.Column("created_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_patients_identifier", "patients", ["identifier"])
    op.create_index("ix_patients_last_name", "patients", ["last_name"])

    op.create_table(
        "practitioner_patient_assignments",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("patient_id", GUID(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("doctor_user_id", GUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ppa_patient_id", "practitioner_patient_assignments", ["patient_id"]
    )
    op.create_index(
        "ix_ppa_doctor_user_id", "practitioner_patient_assignments", ["doctor_user_id"]
    )

    op.create_table(
        "imaging_studies",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("patient_id", GUID(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("study_date", sa.Date(), nullable=False),
        sa.Column("modality", sa.String(50), nullable=False, server_default="Cardiac MRI"),
        sa.Column("status", sa.String(30), nullable=False, server_default="PENDING"),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("created_by", GUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_imaging_studies_patient_id", "imaging_studies", ["patient_id"])
    op.create_index("ix_imaging_studies_study_date", "imaging_studies", ["study_date"])

    op.create_table(
        "clinical_reviews",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "imaging_study_id", GUID(), sa.ForeignKey("imaging_studies.id"), nullable=False
        ),
        sa.Column("reviewer_user_id", GUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(30), nullable=False),
        sa.Column("corrected_diagnosis", sa.String(100), nullable=True),
        sa.Column("comment", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_clinical_reviews_imaging_study_id", "clinical_reviews", ["imaging_study_id"]
    )


def downgrade() -> None:
    op.drop_table("clinical_reviews")
    op.drop_table("imaging_studies")
    op.drop_table("practitioner_patient_assignments")
    op.drop_table("patients")
