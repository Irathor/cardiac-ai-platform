import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.core.enums import ReviewAction, StudyStatus


class StudyOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    study_date: date
    modality: str
    status: str
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class StudyCreateRequest(BaseModel):
    study_date: date
    modality: str = "Cardiac MRI"
    notes: str | None = None


class StudyUpdateRequest(BaseModel):
    status: StudyStatus | None = None
    notes: str | None = None


class ReviewOut(BaseModel):
    id: uuid.UUID
    imaging_study_id: uuid.UUID
    reviewer_user_id: uuid.UUID
    action: str
    corrected_diagnosis: str | None
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewCreateRequest(BaseModel):
    action: ReviewAction
    corrected_diagnosis: str | None = None
    comment: str | None = None
