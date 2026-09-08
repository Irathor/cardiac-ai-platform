import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.patient import Patient
    from app.models.user import User


class PractitionerPatientAssignment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Which doctor can see which patient. A DOCTOR's patient/study queries are
    always scoped through this table — see docs/permissions.md."""

    __tablename__ = "practitioner_patient_assignments"

    patient_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("patients.id"), index=True)
    doctor_user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), index=True)
    assigned_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    # Assignments are soft-ended (not deleted) so history of who could see a
    # patient, and when, is preserved for audit purposes.
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    patient: Mapped["Patient"] = relationship(back_populates="assignments")
    doctor: Mapped["User"] = relationship(foreign_keys=[doctor_user_id])
