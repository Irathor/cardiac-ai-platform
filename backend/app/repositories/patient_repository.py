"""Patient queries — including the DOCTOR scoping that is the platform's
single most important security boundary (see docs/permissions.md).

Every function that lists/reads patients accepts `restrict_to_doctor_id`.
When it is not None, the query is filtered to patients that doctor is
currently (actively) assigned to, at the SQL level — never trust a caller
to have checked this in Python first.
"""
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session

from app.models.ai_analysis import AIAnalysis
from app.models.imaging_study import ImagingStudy
from app.models.patient import Patient
from app.models.practitioner_patient_assignment import PractitionerPatientAssignment
from app.models.user import User

SORTABLE_FIELDS = {"last_name", "first_name", "last_study_date"}

# Below this, a prediction is flagged for the "only low-confidence" patient
# list filter rather than trusted at face value — see docs/clinical-limitations.md.
LOW_CONFIDENCE_THRESHOLD = 0.6


@dataclass
class PatientListRow:
    patient: Patient
    last_study_date: date | None
    last_study_status: str | None
    last_analysis_predicted_class: str | None
    last_analysis_confidence: float | None


def _active_assignment_exists(doctor_id: uuid.UUID):
    return exists(
        select(1).where(
            PractitionerPatientAssignment.patient_id == Patient.id,
            PractitionerPatientAssignment.doctor_user_id == doctor_id,
            PractitionerPatientAssignment.unassigned_at.is_(None),
        )
    )


def _base_query(
    *,
    restrict_to_doctor_id: uuid.UUID | None,
    only_mine_doctor_id: uuid.UUID | None,
    search: str | None,
    study_date_from: date | None,
    study_date_to: date | None,
    diagnosis: str | None,
    analysis_status: str | None,
    low_confidence: bool,
):
    latest_date_subq = (
        select(ImagingStudy.study_date)
        .where(ImagingStudy.patient_id == Patient.id, ImagingStudy.deleted_at.is_(None))
        .order_by(ImagingStudy.study_date.desc())
        .limit(1)
        .correlate(Patient)
        .scalar_subquery()
    )
    latest_status_subq = (
        select(ImagingStudy.status)
        .where(ImagingStudy.patient_id == Patient.id, ImagingStudy.deleted_at.is_(None))
        .order_by(ImagingStudy.study_date.desc())
        .limit(1)
        .correlate(Patient)
        .scalar_subquery()
    )
    _latest_completed_analysis = (
        select(AIAnalysis)
        .join(ImagingStudy, ImagingStudy.id == AIAnalysis.imaging_study_id)
        .where(ImagingStudy.patient_id == Patient.id, AIAnalysis.status == "COMPLETED")
        .order_by(AIAnalysis.created_at.desc())
        .limit(1)
        .correlate(Patient)
    )
    latest_analysis_class_subq = _latest_completed_analysis.with_only_columns(
        AIAnalysis.predicted_class
    ).scalar_subquery()
    latest_analysis_confidence_subq = _latest_completed_analysis.with_only_columns(
        AIAnalysis.confidence
    ).scalar_subquery()

    stmt = select(
        Patient,
        latest_date_subq.label("last_study_date"),
        latest_status_subq.label("last_study_status"),
        latest_analysis_class_subq.label("last_analysis_predicted_class"),
        latest_analysis_confidence_subq.label("last_analysis_confidence"),
    ).where(Patient.deleted_at.is_(None))

    if restrict_to_doctor_id is not None:
        stmt = stmt.where(_active_assignment_exists(restrict_to_doctor_id))
    if only_mine_doctor_id is not None:
        stmt = stmt.where(_active_assignment_exists(only_mine_doctor_id))

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            Patient.first_name.ilike(pattern)
            | Patient.last_name.ilike(pattern)
            | Patient.identifier.ilike(pattern)
        )

    if study_date_from is not None or study_date_to is not None:
        conditions = [ImagingStudy.patient_id == Patient.id, ImagingStudy.deleted_at.is_(None)]
        if study_date_from is not None:
            conditions.append(ImagingStudy.study_date >= study_date_from)
        if study_date_to is not None:
            conditions.append(ImagingStudy.study_date <= study_date_to)
        stmt = stmt.where(exists(select(1).where(and_(*conditions))))

    if diagnosis:
        stmt = stmt.where(Patient.registered_diagnosis == diagnosis)

    if analysis_status:
        stmt = stmt.where(latest_status_subq == analysis_status)

    if low_confidence:
        stmt = stmt.where(latest_analysis_confidence_subq < LOW_CONFIDENCE_THRESHOLD)

    return stmt, latest_date_subq


def list_patients(
    db: Session,
    *,
    restrict_to_doctor_id: uuid.UUID | None,
    only_mine_doctor_id: uuid.UUID | None = None,
    search: str | None = None,
    study_date_from: date | None = None,
    study_date_to: date | None = None,
    diagnosis: str | None = None,
    analysis_status: str | None = None,
    low_confidence: bool = False,
    sort_by: str = "last_name",
    sort_dir: str = "asc",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PatientListRow], int]:
    if sort_by not in SORTABLE_FIELDS:
        sort_by = "last_name"

    stmt, latest_date_subq = _base_query(
        restrict_to_doctor_id=restrict_to_doctor_id,
        only_mine_doctor_id=only_mine_doctor_id,
        search=search,
        study_date_from=study_date_from,
        study_date_to=study_date_to,
        diagnosis=diagnosis,
        analysis_status=analysis_status,
        low_confidence=low_confidence,
    )

    count_stmt = select(func.count()).select_from(stmt.with_only_columns(Patient.id).subquery())
    total = db.execute(count_stmt).scalar_one()

    order_column = {
        "last_name": Patient.last_name,
        "first_name": Patient.first_name,
        "last_study_date": latest_date_subq,
    }[sort_by]
    order_clause = order_column.desc() if sort_dir == "desc" else order_column.asc()
    stmt = stmt.order_by(order_clause, Patient.id).offset((page - 1) * page_size).limit(page_size)

    rows = db.execute(stmt).all()
    return [
        PatientListRow(
            patient=row[0], last_study_date=row[1], last_study_status=row[2],
            last_analysis_predicted_class=row[3], last_analysis_confidence=row[4],
        )
        for row in rows
    ], total


def assigned_doctor_names(db: Session, patient_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[str]]:
    if not patient_ids:
        return {}
    stmt = (
        select(PractitionerPatientAssignment.patient_id, User.full_name)
        .join(User, User.id == PractitionerPatientAssignment.doctor_user_id)
        .where(
            PractitionerPatientAssignment.patient_id.in_(patient_ids),
            PractitionerPatientAssignment.unassigned_at.is_(None),
        )
    )
    result: dict[uuid.UUID, list[str]] = {pid: [] for pid in patient_ids}
    for patient_id, doctor_name in db.execute(stmt).all():
        result[patient_id].append(doctor_name)
    return result


def get_by_id(db: Session, patient_id: uuid.UUID) -> Patient | None:
    stmt = select(Patient).where(Patient.id == patient_id, Patient.deleted_at.is_(None))
    return db.execute(stmt).scalar_one_or_none()


def is_assigned_to_doctor(db: Session, *, patient_id: uuid.UUID, doctor_id: uuid.UUID) -> bool:
    stmt = select(
        exists(
            select(1).where(
                PractitionerPatientAssignment.patient_id == patient_id,
                PractitionerPatientAssignment.doctor_user_id == doctor_id,
                PractitionerPatientAssignment.unassigned_at.is_(None),
            )
        )
    )
    return bool(db.execute(stmt).scalar_one())


def create(db: Session, *, organization_id: uuid.UUID, created_by: uuid.UUID | None, **fields) -> Patient:
    patient = Patient(organization_id=organization_id, created_by=created_by, **fields)
    db.add(patient)
    db.flush()
    return patient


def create_assignment(
    db: Session, *, patient_id: uuid.UUID, doctor_user_id: uuid.UUID, assigned_by: uuid.UUID | None
) -> PractitionerPatientAssignment:
    assignment = PractitionerPatientAssignment(
        patient_id=patient_id, doctor_user_id=doctor_user_id, assigned_by=assigned_by
    )
    db.add(assignment)
    db.flush()
    return assignment
