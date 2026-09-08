import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.roles import RoleName
from app.db.session import get_db
from app.models.annotation import Annotation
from app.models.segmentation import Segmentation
from app.models.user import User
from app.repositories import annotation_repository, image_series_repository, segmentation_repository
from app.schemas.annotation import (
    AnnotationOut,
    AnnotationRequestCreate,
    AnnotationReviewRequest,
)
from app.services import annotation_service, patient_service, study_service

router = APIRouter()

_SEGMENTATION_NOT_FOUND = "Segmentation not found"
_ANNOTATION_NOT_FOUND = "Annotation not found"


def _load_segmentation_for_viewer(db: Session, segmentation_id: uuid.UUID, viewer: User) -> Segmentation:
    segmentation = segmentation_repository.get_by_id(db, segmentation_id)
    if segmentation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SEGMENTATION_NOT_FOUND)
    series = image_series_repository.get_by_id(db, segmentation.image_series_id)
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SEGMENTATION_NOT_FOUND)
    try:
        study_service.get_study_for_viewer(db, series.imaging_study_id, viewer)
    except study_service.StudyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SEGMENTATION_NOT_FOUND) from exc
    return segmentation


def _load_annotation_for_reviewer(db: Session, annotation_id: uuid.UUID, viewer: User) -> Annotation:
    """A DOCTOR/ADMIN may see an annotation only if they can see the patient
    it ultimately belongs to — same non-disclosure rule as everywhere else."""
    annotation = annotation_repository.get_by_id(db, annotation_id)
    if annotation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ANNOTATION_NOT_FOUND)
    patient_id = annotation_repository.get_patient_id(db, annotation)
    if patient_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ANNOTATION_NOT_FOUND)
    try:
        patient_service.get_patient_for_viewer(db, patient_id, viewer)
    except patient_service.PatientNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ANNOTATION_NOT_FOUND) from exc
    return annotation


def _load_annotation_for_annotator(db: Session, annotation_id: uuid.UUID, annotator: User) -> Annotation:
    """An ANNOTATOR may only see/edit cases assigned to them (see
    docs/permissions.md — "View only assigned annotation cases")."""
    annotation = annotation_repository.get_by_id(db, annotation_id)
    if annotation is None or annotation.annotator_id != annotator.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ANNOTATION_NOT_FOUND)
    return annotation


@router.post("/segmentations/{segmentation_id}/annotations", status_code=status.HTTP_201_CREATED)
def request_annotation(
    segmentation_id: uuid.UUID,
    payload: AnnotationRequestCreate,
    db: Session = Depends(get_db),
    doctor: User = Depends(require_roles(RoleName.DOCTOR)),
) -> AnnotationOut:
    segmentation = _load_segmentation_for_viewer(db, segmentation_id, doctor)
    try:
        annotation = annotation_service.request_annotation(
            db, requesting_doctor=doctor, segmentation=segmentation,
            annotator_user_id=payload.annotator_user_id,
        )
    except annotation_service.AnnotatorNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown or non-ANNOTATOR user"
        ) from exc
    db.commit()
    db.refresh(annotation)
    return AnnotationOut.model_validate(annotation)


@router.get("/segmentations/{segmentation_id}/annotations")
def list_annotations_for_segmentation(
    segmentation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> list[AnnotationOut]:
    _load_segmentation_for_viewer(db, segmentation_id, current_user)
    return [
        AnnotationOut.model_validate(a)
        for a in annotation_repository.list_for_segmentation(db, segmentation_id)
    ]


@router.get("/annotations/mine")
def list_my_annotations(
    db: Session = Depends(get_db),
    annotator: User = Depends(require_roles(RoleName.ANNOTATOR)),
) -> list[AnnotationOut]:
    return [AnnotationOut.model_validate(a) for a in annotation_repository.list_for_annotator(db, annotator.id)]


@router.get("/annotations/{annotation_id}")
def get_annotation(
    annotation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR, RoleName.ANNOTATOR)),
) -> AnnotationOut:
    can_review = {RoleName.ADMIN.value, RoleName.DOCTOR.value} & current_user.role_names
    if can_review:
        annotation = _load_annotation_for_reviewer(db, annotation_id, current_user)
    else:
        annotation = _load_annotation_for_annotator(db, annotation_id, current_user)
    return AnnotationOut.model_validate(annotation)


@router.patch("/annotations/{annotation_id}")
async def update_annotation_draft(
    annotation_id: uuid.UUID,
    diagnosis_label: str | None = Form(None),
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    annotator: User = Depends(require_roles(RoleName.ANNOTATOR)),
) -> AnnotationOut:
    annotation = _load_annotation_for_annotator(db, annotation_id, annotator)
    corrected_mask_bytes = await file.read() if file is not None else None
    try:
        annotation = annotation_service.save_draft(
            db, actor=annotator, annotation=annotation,
            diagnosis_label=diagnosis_label, corrected_mask_bytes=corrected_mask_bytes,
        )
    except annotation_service.InvalidAnnotationStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except annotation_service.InvalidDiagnosisLabelError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    db.refresh(annotation)
    return AnnotationOut.model_validate(annotation)


@router.post("/annotations/{annotation_id}/submit")
def submit_annotation(
    annotation_id: uuid.UUID,
    db: Session = Depends(get_db),
    annotator: User = Depends(require_roles(RoleName.ANNOTATOR)),
) -> AnnotationOut:
    annotation = _load_annotation_for_annotator(db, annotation_id, annotator)
    try:
        annotation = annotation_service.submit(db, actor=annotator, annotation=annotation)
    except annotation_service.InvalidAnnotationStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(annotation)
    return AnnotationOut.model_validate(annotation)


@router.post("/annotations/{annotation_id}/review")
def review_annotation(
    annotation_id: uuid.UUID,
    payload: AnnotationReviewRequest,
    db: Session = Depends(get_db),
    doctor: User = Depends(require_roles(RoleName.DOCTOR)),
) -> AnnotationOut:
    annotation = _load_annotation_for_reviewer(db, annotation_id, doctor)
    try:
        annotation = annotation_service.review(
            db, reviewer=doctor, annotation=annotation, approve=payload.approve, comment=payload.comment,
        )
    except annotation_service.InvalidAnnotationStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(annotation)
    return AnnotationOut.model_validate(annotation)
