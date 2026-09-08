import uuid
from datetime import datetime

from pydantic import BaseModel


class DatasetOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetCreateRequest(BaseModel):
    name: str
    description: str | None = None


class DatasetVersionOut(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    version_number: int
    status: str
    checksum: str | None
    created_at: datetime
    locked_at: datetime | None

    model_config = {"from_attributes": True}


class DatasetCaseOut(BaseModel):
    id: uuid.UUID
    dataset_version_id: uuid.UUID
    patient_id: uuid.UUID
    annotation_id: uuid.UUID
    split: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DatasetCaseCreateRequest(BaseModel):
    annotation_id: uuid.UUID
    split: str
