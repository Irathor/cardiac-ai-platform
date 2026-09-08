import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import _utcnow

if TYPE_CHECKING:
    from app.models.imaging_study import ImagingStudy
    from app.models.user import User


class ClinicalReview(Base):
    """One row per review action. Never updated or deleted — a correction
    is a *new* row, so the original prediction/decision is always preserved
    (see docs/permissions.md and the spec's "no sobrescribas" rule)."""

    __tablename__ = "clinical_reviews"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    imaging_study_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("imaging_studies.id"), index=True
    )
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"))

    # One of app.core.enums.ReviewAction.
    action: Mapped[str] = mapped_column(String(30))
    corrected_diagnosis: Mapped[str | None] = mapped_column(String(100))
    comment: Mapped[str | None] = mapped_column(String(2000))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    study: Mapped["ImagingStudy"] = relationship(back_populates="reviews")
    reviewer: Mapped["User"] = relationship(foreign_keys=[reviewer_user_id])
