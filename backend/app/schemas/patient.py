import uuid
from datetime import date, datetime

from pydantic import BaseModel


class PatientListItem(BaseModel):
    id: uuid.UUID
    identifier: str
    first_name: str
    last_name: str
    date_of_birth: date
    registered_diagnosis: str | None
    last_study_date: date | None
    last_study_status: str | None
    last_analysis_predicted_class: str | None
    last_analysis_confidence: float | None
    assigned_doctor_names: list[str]

    model_config = {"from_attributes": True}


class PatientPage(BaseModel):
    items: list[PatientListItem]
    total: int
    page: int
    page_size: int


class PatientDetail(BaseModel):
    id: uuid.UUID
    identifier: str
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str | None
    height_cm: float | None
    weight_kg: float | None
    registered_diagnosis: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PatientCreateRequest(BaseModel):
    identifier: str
    first_name: str
    last_name: str
    date_of_birth: date
    sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    registered_diagnosis: str | None = None


class PatientUpdateRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    sex: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    registered_diagnosis: str | None = None


class AssignmentCreateRequest(BaseModel):
    patient_id: uuid.UUID
    doctor_user_id: uuid.UUID


class AssignmentOut(BaseModel):
    id: uuid.UUID
    patient_id: uuid.UUID
    doctor_user_id: uuid.UUID
    unassigned_at: datetime | None

    model_config = {"from_attributes": True}
