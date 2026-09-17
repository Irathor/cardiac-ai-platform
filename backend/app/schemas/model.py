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
    accuracy: float | None
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


class ModelRegistryDivergenceOut(BaseModel):
    model_version_id: uuid.UUID
    local_status: str
    expected_alias: str | None
    actual_alias: str | None
    fetch_error: str | None = None


class BiomarkerDriftOut(BaseModel):
    biomarker_name: str
    ks_statistic: float | None
    p_value: float | None
    base_sample_size: int
    recent_sample_size: int
    drift_detected: bool
    skipped_reason: str | None

    model_config = {"from_attributes": True}


class PredictionDriftOut(BaseModel):
    psi: float | None
    base_sample_size: int
    recent_sample_size: int
    severity: str
    drift_detected: bool
    skipped_reason: str | None

    model_config = {"from_attributes": True}


class ModelDriftOut(BaseModel):
    model_version_id: uuid.UUID
    evaluated_at: datetime
    biomarkers: list[BiomarkerDriftOut]
    biomarkers_skipped_reason: str | None
    prediction: PredictionDriftOut

    model_config = {"from_attributes": True}
