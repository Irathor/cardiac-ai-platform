import uuid

from sqlalchemy.orm import Session

from app.models.imaging_study import ImagingStudy
from app.models.patient import Patient
from app.models.user import User
from app.repositories import audit_repository, study_repository
from app.services import patient_service


class StudyNotFoundError(Exception):
    """Raised both when the study truly doesn't exist and when the viewer
    can't see the patient it belongs to — same non-disclosure rule as
    patient_service.PatientNotFoundError."""


def get_study_for_viewer(db: Session, study_id: uuid.UUID, viewer: User) -> ImagingStudy:
    """Loads a study while enforcing the same DOCTOR-must-be-assigned rule
    used for patients — a study is only ever reachable through a patient
    the viewer is allowed to see (see docs/permissions.md)."""
    study = study_repository.get_by_id(db, study_id)
    if study is None:
        raise StudyNotFoundError()
    try:
        patient_service.get_patient_for_viewer(db, study.patient_id, viewer)
    except patient_service.PatientNotFoundError as exc:
        raise StudyNotFoundError() from exc
    return study


def create_study(db: Session, *, actor: User, patient: Patient, **fields) -> ImagingStudy:
    study = study_repository.create(db, patient_id=patient.id, created_by=actor.id, **fields)
    audit_repository.record(
        db, user_id=actor.id, action="study_created", resource_type="imaging_study",
        resource_id=str(study.id), result="success",
    )
    return study


def update_study(db: Session, *, actor: User, study: ImagingStudy, **fields) -> ImagingStudy:
    for key, value in fields.items():
        if value is not None:
            setattr(study, key, value)
    db.flush()
    audit_repository.record(
        db, user_id=actor.id, action="study_updated", resource_type="imaging_study",
        resource_id=str(study.id), result="success", event_metadata=fields,
    )
    return study


def create_review(db: Session, *, reviewer: User, study: ImagingStudy, **fields):
    review = study_repository.create_review(
        db, imaging_study_id=study.id, reviewer_user_id=reviewer.id, **fields
    )
    audit_repository.record(
        db, user_id=reviewer.id, action="clinical_review_created", resource_type="imaging_study",
        resource_id=str(study.id), result="success",
        event_metadata={"review_id": str(review.id), "action": fields.get("action")},
    )
    return review
