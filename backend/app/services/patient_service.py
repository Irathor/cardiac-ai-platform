"""Patient/assignment business rules, including the DOCTOR access boundary.

`get_patient_for_viewer` is the single choke point every patient-detail-ish
endpoint (study list, study detail, reviews) must go through — it is what
makes "a doctor can only see assigned patients" true even against a
hand-crafted request with someone else's patient UUID in the URL.
"""
import uuid

from sqlalchemy.orm import Session

from app.core.roles import RoleName
from app.models.patient import Patient
from app.models.user import User
from app.repositories import audit_repository, patient_repository, user_repository


class PatientNotFoundError(Exception):
    """Raised both when the patient truly doesn't exist and when the viewer
    is a DOCTOR with no assignment to it — the two cases are indistinguishable
    from the outside on purpose (never confirm a patient's existence to a
    doctor who isn't assigned to them)."""


class DoctorNotFoundError(Exception):
    pass


def is_admin(user: User) -> bool:
    return RoleName.ADMIN.value in user.role_names


def get_patient_for_viewer(db: Session, patient_id: uuid.UUID, viewer: User) -> Patient:
    patient = patient_repository.get_by_id(db, patient_id)
    if patient is None:
        raise PatientNotFoundError()

    if is_admin(viewer):
        return patient

    if not patient_repository.is_assigned_to_doctor(
        db, patient_id=patient_id, doctor_id=viewer.id
    ):
        raise PatientNotFoundError()

    return patient


def list_patients_for_viewer(db: Session, viewer: User, *, only_mine: bool = False, **filters):
    restrict_to_doctor_id = None if is_admin(viewer) else viewer.id
    only_mine_doctor_id = viewer.id if only_mine else None
    return patient_repository.list_patients(
        db,
        restrict_to_doctor_id=restrict_to_doctor_id,
        only_mine_doctor_id=only_mine_doctor_id,
        **filters,
    )


def create_patient(db: Session, *, admin: User, **fields) -> Patient:
    patient = patient_repository.create(
        db, organization_id=admin.organization_id, created_by=admin.id, **fields
    )
    audit_repository.record(
        db, user_id=admin.id, action="patient_created", resource_type="patient",
        resource_id=str(patient.id), result="success",
    )
    return patient


def assign_doctor(db: Session, *, admin: User, patient: Patient, doctor_user_id: uuid.UUID):
    doctor = user_repository.get_by_id(db, doctor_user_id)
    if doctor is None or RoleName.DOCTOR.value not in doctor.role_names:
        raise DoctorNotFoundError()

    assignment = patient_repository.create_assignment(
        db, patient_id=patient.id, doctor_user_id=doctor_user_id, assigned_by=admin.id
    )
    audit_repository.record(
        db, user_id=admin.id, action="patient_assigned", resource_type="patient",
        resource_id=str(patient.id), result="success",
        event_metadata={"doctor_user_id": str(doctor_user_id)},
    )
    return assignment
