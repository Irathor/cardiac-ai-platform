import uuid
from datetime import datetime

from pydantic import BaseModel


class TrainingRunOut(BaseModel):
    id: uuid.UUID
    dataset_version_id: uuid.UUID
    status: str
    mlflow_run_id: str | None
    metrics: dict | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
