import uuid
from datetime import datetime

from pydantic import BaseModel


class ModelVersionOut(BaseModel):
    id: uuid.UUID
    training_run_id: uuid.UUID
    name: str
    mlflow_run_id: str
    mlflow_model_uri: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelEvaluationOut(BaseModel):
    id: uuid.UUID
    model_version_id: uuid.UUID
    split: str
    accuracy: float
    metrics: dict
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelApprovalOut(BaseModel):
    id: uuid.UUID
    model_version_id: uuid.UUID
    approver_id: uuid.UUID
    decision: str
    justification: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ModelReviewRequest(BaseModel):
    approve: bool
    justification: str


class ModelPromoteRequest(BaseModel):
    justification: str
