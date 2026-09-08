import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.imaging_study import ImagingStudy
    from app.models.practitioner_patient_assignment import PractitionerPatientAssignment


class Patient(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A fictitious or anonymized research subject. Never real, identifiable
    patient data — see docs/clinical-limitations.md."""

    __tablename__ = "patients"

    organization_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("organizations.id"))

    # Artificial identifier (e.g. "PT-00001"), distinct from the DB primary
    # key so it can be shown/searched without exposing the internal UUID.
    identifier: Mapped[str] = mapped_column(String(50), unique=True, index=True)

    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100), index=True)
    date_of_birth: Mapped[date] = mapped_column(Date())
    sex: Mapped[str | None] = mapped_column(String(20))

    # Optional, used for indexed biomarkers once Phase 4 computes them.
    height_cm: Mapped[float | None] = mapped_column(Float())
    weight_kg: Mapped[float | None] = mapped_column(Float())

    registered_diagnosis: Mapped[str | None] = mapped_column(String(100))

    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    assignments: Mapped[list["PractitionerPatientAssignment"]] = relationship(
        back_populates="patient"
    )
    studies: Mapped[list["ImagingStudy"]] = relationship(back_populates="patient")
