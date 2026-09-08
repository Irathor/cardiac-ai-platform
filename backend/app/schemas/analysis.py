import uuid
from datetime import datetime

from pydantic import BaseModel


class AIAnalysisOut(BaseModel):
    id: uuid.UUID
    imaging_study_id: uuid.UUID
    status: str
    model_version: str
    features: dict[str, float] | None
    predicted_class: str | None
    probabilities: dict[str, float] | None
    confidence: float | None
    feature_attributions: dict[str, float] | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
