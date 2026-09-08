import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ModelVersionStatus
from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.model_approval import ModelApproval
    from app.models.model_evaluation import ModelEvaluation
    from app.models.training_run import TrainingRun


class ModelVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A candidate (or, once PRODUCTION, active) classifier.

    `prototypes` is the actual model artifact the live nearest-centroid
    inference path consumes (see app.services.analysis_service) — a plain
    JSON copy of what was logged to MLflow at `mlflow_run_id`/`mlflow_model_uri`,
    kept here so a live analysis request never needs to fetch an artifact
    from MLflow (see docs/architecture.md: MLflow is the source of truth for
    training history, but the request/response path must stay independent of
    it). Null for U-Net/CNN3D model versions — those are real checkpoint
    files (logged to MLflow as an artifact, see mlflow_model_uri), not a
    JSON-serializable prototypes dict, and analysis_service never reads them.
    Soft-delete only — never hard-deleted once it may have produced analyses.
    """

    __tablename__ = "model_versions"

    training_run_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("training_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    mlflow_run_id: Mapped[str] = mapped_column(String(100))
    mlflow_model_uri: Mapped[str] = mapped_column(String(500))
    prototypes: Mapped[dict | None] = mapped_column(JSON())
    status: Mapped[str] = mapped_column(
        String(20), default=ModelVersionStatus.PENDING_REVIEW.value, index=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    training_run: Mapped["TrainingRun"] = relationship(back_populates="model_versions")
    evaluations: Mapped[list["ModelEvaluation"]] = relationship(back_populates="model_version")
    approvals: Mapped[list["ModelApproval"]] = relationship(back_populates="model_version")
