import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.roles import RoleName
from app.db.session import get_db
from app.models.user import User
from app.repositories import patient_repository, study_repository
from app.schemas.patient import (
    AssignmentCreateRequest,
    AssignmentOut,
    PatientCreateRequest,
    PatientDetail,
    PatientListItem,
    PatientPage,
    PatientUpdateRequest,
)
from app.schemas.study import StudyCreateRequest, StudyOut
from app.services import patient_service, study_service

router = APIRouter()

_PATIENT_NOT_FOUND = "Patient not found"


@router.get("")
def list_patients(
    search: str | None = Query(None),
    study_date_from: date | None = Query(None),
    study_date_to: date | None = Query(None),
    diagnosis: str | None = Query(None),
    analysis_status: str | None = Query(None),
    low_confidence: bool = Query(False),
    only_mine: bool = Query(False),
    sort_by: str = Query("last_name"),
    sort_dir: str = Query("asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> PatientPage:
    rows, total = patient_service.list_patients_for_viewer(
        db,
        current_user,
        only_mine=only_mine,
        search=search,
        study_date_from=study_date_from,
        study_date_to=study_date_to,
        diagnosis=diagnosis,
        analysis_status=analysis_status,
        low_confidence=low_confidence,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
    )
    doctor_names = patient_repository.assigned_doctor_names(db, [r.patient.id for r in rows])
    items = [
        PatientListItem(
            id=row.patient.id,
            identifier=row.patient.identifier,
            first_name=row.patient.first_name,
            last_name=row.patient.last_name,
            date_of_birth=row.patient.date_of_birth,
            registered_diagnosis=row.patient.registered_diagnosis,
            last_study_date=row.last_study_date,
            last_study_status=row.last_study_status,
            last_analysis_predicted_class=row.last_analysis_predicted_class,
            last_analysis_confidence=row.last_analysis_confidence,
            assigned_doctor_names=doctor_names.get(row.patient.id, []),
        )
        for row in rows
    ]
    return PatientPage(items=items, total=total, page=page, page_size=page_size)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_patient(
    payload: PatientCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(RoleName.ADMIN)),
) -> PatientDetail:
    patient = patient_service.create_patient(db, admin=admin, **payload.model_dump())
    db.commit()
    db.refresh(patient)
    return PatientDetail.model_validate(patient)


@router.get("/{patient_id}")
def get_patient(
    patient_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> PatientDetail:
    try:
        patient = patient_service.get_patient_for_viewer(db, patient_id, current_user)
    except patient_service.PatientNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PATIENT_NOT_FOUND) from exc
    return PatientDetail.model_validate(patient)


@router.patch("/{patient_id}")
def update_patient(
    patient_id: uuid.UUID,
    payload: PatientUpdateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(RoleName.ADMIN)),
) -> PatientDetail:
    patient = patient_repository.get_by_id(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PATIENT_NOT_FOUND)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(patient, key, value)
    db.commit()
    db.refresh(patient)
    return PatientDetail.model_validate(patient)


@router.post("/{patient_id}/assignments", status_code=status.HTTP_201_CREATED)
def assign_doctor(
    patient_id: uuid.UUID,
    payload: AssignmentCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(RoleName.ADMIN)),
) -> AssignmentOut:
    patient = patient_repository.get_by_id(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PATIENT_NOT_FOUND)
    try:
        assignment = patient_service.assign_doctor(
            db, admin=admin, patient=patient, doctor_user_id=payload.doctor_user_id
        )
    except patient_service.DoctorNotFoundError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown or non-DOCTOR user"
        ) from exc
    db.commit()
    db.refresh(assignment)
    return AssignmentOut.model_validate(assignment)


@router.get("/{patient_id}/studies")
def list_studies(
    patient_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> list[StudyOut]:
    try:
        patient_service.get_patient_for_viewer(db, patient_id, current_user)
    except patient_service.PatientNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PATIENT_NOT_FOUND) from exc

    return [StudyOut.model_validate(s) for s in study_repository.list_for_patient(db, patient_id)]


@router.post("/{patient_id}/studies", status_code=status.HTTP_201_CREATED)
def create_study(
    patient_id: uuid.UUID,
    payload: StudyCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_roles(RoleName.ADMIN)),
) -> StudyOut:
    patient = patient_repository.get_by_id(db, patient_id)
    if patient is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_PATIENT_NOT_FOUND)
    study = study_service.create_study(db, actor=admin, patient=patient, **payload.model_dump())
    db.commit()
    db.refresh(study)
    return StudyOut.model_validate(study)
