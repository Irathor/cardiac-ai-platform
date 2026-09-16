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
    # EPIC-3: whether GET /analyses/{id}/gradcam has an attribution map to
    # serve for this analysis, and the honest reason when it doesn't (only
    # ever set for a CNN3D_CLASSIFICATION analysis where Grad-CAM itself
    # failed — never for the tabular nearest-centroid path, where there's no
    # image-native attribution to compute in the first place). Mirrors
    # AIAnalysis.gradcam_available (a plain `gradcam_storage_key is not None`
    # property, not a stored column).
    gradcam_available: bool
    gradcam_error: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
