import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import StudyStatus
from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.clinical_review import ClinicalReview
    from app.models.patient import Patient


class ImagingStudy(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "imaging_studies"

    patient_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("patients.id"), index=True)
    study_date: Mapped[date] = mapped_column(Date(), index=True)
    modality: Mapped[str] = mapped_column(String(50), default="Cardiac MRI")
    status: Mapped[str] = mapped_column(String(30), default=StudyStatus.PENDING.value)
    notes: Mapped[str | None] = mapped_column(String(2000))

    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    patient: Mapped["Patient"] = relationship(back_populates="studies")
    reviews: Mapped[list["ClinicalReview"]] = relationship(back_populates="study")
