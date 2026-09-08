import uuid
from datetime import datetime

from pydantic import BaseModel


class AnnotationOut(BaseModel):
    id: uuid.UUID
    based_on_segmentation_id: uuid.UUID
    annotator_id: uuid.UUID
    requested_by: uuid.UUID | None
    status: str
    corrected_segmentation_id: uuid.UUID | None
    diagnosis_label: str | None
    reviewer_id: uuid.UUID | None
    review_comment: str | None
    submitted_at: datetime | None
    reviewed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AnnotationRequestCreate(BaseModel):
    annotator_user_id: uuid.UUID


class AnnotationReviewRequest(BaseModel):
    approve: bool
    comment: str | None = None
