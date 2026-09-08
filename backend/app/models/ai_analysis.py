import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AnalysisStatus
from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.imaging_study import ImagingStudy


class AIAnalysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One asynchronous disease-classification run for an ImagingStudy.

    Stores full per-class probabilities (not just the top class) and a
    feature attribution map, so a low-confidence or surprising result can
    always be inspected rather than trusted blindly — see
    docs/clinical-limitations.md. `model_version` is a demo-mode heuristic
    identifier until Phase 7 registers a real MLflow model version.
    """

    __tablename__ = "ai_analyses"

    imaging_study_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("imaging_studies.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=AnalysisStatus.QUEUED.value, index=True)
    model_version: Mapped[str] = mapped_column(String(200))

    features: Mapped[dict | None] = mapped_column(JSON())
    predicted_class: Mapped[str | None] = mapped_column(String(100))
    probabilities: Mapped[dict | None] = mapped_column(JSON())
    # Denormalized from probabilities[predicted_class] at completion time —
    # kept as its own column (rather than computed on read) so the patient
    # list's low-confidence filter (see patient_repository.list_patients) can
    # do a plain, portable `WHERE confidence < x` instead of a per-dialect
    # JSON key lookup keyed by a dynamic (predicted_class) key.
    confidence: Mapped[float | None] = mapped_column(Float())
    feature_attributions: Mapped[dict | None] = mapped_column(JSON())
    error_message: Mapped[str | None] = mapped_column(String(2000))

    requested_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    imaging_study: Mapped["ImagingStudy"] = relationship()
