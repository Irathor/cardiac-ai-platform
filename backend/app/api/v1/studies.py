import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.roles import RoleName
from app.db.session import get_db
from app.models.imaging_study import ImagingStudy
from app.models.user import User
from app.repositories import study_repository
from app.schemas.study import ReviewCreateRequest, ReviewOut, StudyOut, StudyUpdateRequest
from app.services import study_service

router = APIRouter()

_STUDY_NOT_FOUND = "Study not found"


def _load_study_for_viewer(db: Session, study_id: uuid.UUID, viewer: User) -> ImagingStudy:
    try:
        return study_service.get_study_for_viewer(db, study_id, viewer)
    except study_service.StudyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_STUDY_NOT_FOUND) from exc


@router.get("/{study_id}")
def get_study(
    study_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> StudyOut:
    study = _load_study_for_viewer(db, study_id, current_user)
    return StudyOut.model_validate(study)


@router.patch("/{study_id}")
def update_study(
    study_id: uuid.UUID,
    payload: StudyUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> StudyOut:
    study = _load_study_for_viewer(db, study_id, current_user)
    fields = payload.model_dump(exclude_unset=True)
    if "status" in fields and fields["status"] is not None:
        fields["status"] = fields["status"].value
    study = study_service.update_study(db, actor=current_user, study=study, **fields)
    db.commit()
    db.refresh(study)
    return StudyOut.model_validate(study)


@router.get("/{study_id}/reviews")
def list_reviews(
    study_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> list[ReviewOut]:
    _load_study_for_viewer(db, study_id, current_user)
    return [ReviewOut.model_validate(r) for r in study_repository.list_reviews(db, study_id)]


@router.post("/{study_id}/reviews", status_code=status.HTTP_201_CREATED)
def create_review(
    study_id: uuid.UUID,
    payload: ReviewCreateRequest,
    db: Session = Depends(get_db),
    doctor: User = Depends(require_roles(RoleName.DOCTOR)),
) -> ReviewOut:
    study = _load_study_for_viewer(db, study_id, doctor)
    review = study_service.create_review(
        db,
        reviewer=doctor,
        study=study,
        action=payload.action.value,
        corrected_diagnosis=payload.corrected_diagnosis,
        comment=payload.comment,
    )
    db.commit()
    db.refresh(review)
    return ReviewOut.model_validate(review)
