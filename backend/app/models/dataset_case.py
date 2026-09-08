import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.dataset_version import DatasetVersion


class DatasetCase(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One approved-annotation case included in a DatasetVersion.

    `patient_id` is denormalized from the annotation's underlying patient
    specifically so patient-level split integrity (no patient's cases spread
    across TRAIN/VALIDATION/TEST — see docs/phases.md) can be checked and
    enforced with a plain query, without walking
    annotation -> segmentation -> series -> study -> patient every time.
    """

    __tablename__ = "dataset_cases"
    __table_args__ = (
        UniqueConstraint("dataset_version_id", "annotation_id", name="uq_dataset_case_annotation"),
    )

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("dataset_versions.id"), index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("patients.id"), index=True)
    annotation_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("annotations.id"))
    split: Mapped[str] = mapped_column(String(20))

    dataset_version: Mapped["DatasetVersion"] = relationship(back_populates="cases")
