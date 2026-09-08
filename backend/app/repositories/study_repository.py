import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.clinical_review import ClinicalReview
from app.models.imaging_study import ImagingStudy


def list_for_patient(db: Session, patient_id: uuid.UUID) -> list[ImagingStudy]:
    stmt = (
        select(ImagingStudy)
        .where(ImagingStudy.patient_id == patient_id, ImagingStudy.deleted_at.is_(None))
        .order_by(ImagingStudy.study_date.desc())
    )
    return list(db.execute(stmt).scalars())


def get_by_id(db: Session, study_id: uuid.UUID) -> ImagingStudy | None:
    stmt = select(ImagingStudy).where(
        ImagingStudy.id == study_id, ImagingStudy.deleted_at.is_(None)
    )
    return db.execute(stmt).scalar_one_or_none()


def create(db: Session, *, patient_id: uuid.UUID, created_by: uuid.UUID | None, **fields) -> ImagingStudy:
    study = ImagingStudy(patient_id=patient_id, created_by=created_by, **fields)
    db.add(study)
    db.flush()
    return study


def list_reviews(db: Session, imaging_study_id: uuid.UUID) -> list[ClinicalReview]:
    stmt = (
        select(ClinicalReview)
        .where(ClinicalReview.imaging_study_id == imaging_study_id)
        .order_by(ClinicalReview.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


def create_review(
    db: Session, *, imaging_study_id: uuid.UUID, reviewer_user_id: uuid.UUID, **fields
) -> ClinicalReview:
    review = ClinicalReview(
        imaging_study_id=imaging_study_id, reviewer_user_id=reviewer_user_id, **fields
    )
    db.add(review)
    db.flush()
    return review
