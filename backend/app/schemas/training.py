import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.enums import TrainingModelType


class TrainingRunOut(BaseModel):
    id: uuid.UUID
    dataset_version_id: uuid.UUID | None
    model_type: str
    status: str
    mlflow_run_id: str | None
    metrics: dict | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TrainingRunRequest(BaseModel):
    """Optional POST body — omitted entirely, old callers keep training the
    nearest-centroid classifier exactly as before (see
    app.services.training_service.create_training_run)."""

    model_type: TrainingModelType = TrainingModelType.NEAREST_CENTROID
