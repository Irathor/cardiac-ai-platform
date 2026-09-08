import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import TrainingRunStatus
from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.dataset_version import DatasetVersion
    from app.models.model_version import ModelVersion


class TrainingRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One "smoke training" job (see ml.cardiac_ai_ml.training — a genuine
    but deliberately lightweight nearest-centroid fit, not a deep-learning
    pipeline this environment has no data/GPU to run) over a LOCKED
    DatasetVersion's TRAIN split, evaluated on its TEST split.
    """

    __tablename__ = "training_runs"

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("dataset_versions.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=TrainingRunStatus.QUEUED.value, index=True)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(100))
    requested_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    metrics: Mapped[dict | None] = mapped_column(JSON())
    error_message: Mapped[str | None] = mapped_column(String(2000))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    dataset_version: Mapped["DatasetVersion"] = relationship()
    model_versions: Mapped[list["ModelVersion"]] = relationship(back_populates="training_run")
