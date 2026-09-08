"""Annotation workflow: DOCTOR sends a segmentation for correction, the
assigned ANNOTATOR edits a draft (optionally uploading a corrected mask and/or
setting a diagnosis label) and submits it, and a DOCTOR reviews it into
APPROVED (ground truth, usable in a dataset) or REJECTED (back to the
annotator with a comment) — see docs/permissions.md and docs/data-dictionary.md.
"""
import uuid
from datetime import datetime, timezone

from cardiac_ai_ml.classification import DiagnosisClass
from sqlalchemy.orm import Session

from app.core.enums import AnnotationStatus
from app.core.roles import RoleName
from app.models.annotation import Annotation
from app.models.segmentation import Segmentation
from app.models.user import User
from app.repositories import annotation_repository, audit_repository, user_repository
from app.services import imaging_service

ALLOWED_DIAGNOSIS_LABELS = {d.value for d in DiagnosisClass}


class AnnotatorNotFoundError(Exception):
    pass


class AnnotationNotFoundError(Exception):
    """Raised both when the annotation truly doesn't exist and when the
    viewer isn't allowed to see it — same non-disclosure convention as
    PatientNotFoundError/StudyNotFoundError."""


class InvalidAnnotationStateError(ValueError):
    pass


class InvalidDiagnosisLabelError(ValueError):
    pass


def _is_annotator_role(user: User) -> bool:
    return RoleName.ANNOTATOR.value in user.role_names


def request_annotation(
    db: Session, *, requesting_doctor: User, segmentation: Segmentation, annotator_user_id: uuid.UUID
) -> Annotation:
    annotator = user_repository.get_by_id(db, annotator_user_id)
    if annotator is None or not _is_annotator_role(annotator):
        raise AnnotatorNotFoundError()

    annotation = annotation_repository.create(
        db, based_on_segmentation_id=segmentation.id, annotator_id=annotator.id,
        requested_by=requesting_doctor.id, status=AnnotationStatus.DRAFT.value,
    )
    audit_repository.record(
        db, user_id=requesting_doctor.id, action="annotation_requested", resource_type="annotation",
        resource_id=str(annotation.id), result="success",
        event_metadata={"segmentation_id": str(segmentation.id), "annotator_id": str(annotator.id)},
    )
    return annotation


def save_draft(
    db: Session, *, actor: User, annotation: Annotation,
    diagnosis_label: str | None = None, corrected_mask_bytes: bytes | None = None,
) -> Annotation:
    if annotation.status != AnnotationStatus.DRAFT.value:
        raise InvalidAnnotationStateError("annotation can only be edited while DRAFT")

    if diagnosis_label is not None:
        if diagnosis_label not in ALLOWED_DIAGNOSIS_LABELS:
            raise InvalidDiagnosisLabelError(
                f"diagnosis_label must be one of {sorted(ALLOWED_DIAGNOSIS_LABELS)}"
            )
        annotation.diagnosis_label = diagnosis_label

    if corrected_mask_bytes is not None:
        series = annotation.based_on_segmentation.image_series
        corrected = imaging_service.upload_segmentation(
            db, actor=actor, series=series, file_bytes=corrected_mask_bytes,
            model_version="manual-correction",
        )
        annotation.corrected_segmentation_id = corrected.id

    db.flush()
    audit_repository.record(
        db, user_id=actor.id, action="annotation_draft_saved", resource_type="annotation",
        resource_id=str(annotation.id), result="success",
    )
    return annotation


def submit(db: Session, *, actor: User, annotation: Annotation) -> Annotation:
    if annotation.status != AnnotationStatus.DRAFT.value:
        raise InvalidAnnotationStateError("annotation can only be submitted while DRAFT")
    if annotation.diagnosis_label is None and annotation.corrected_segmentation_id is None:
        raise InvalidAnnotationStateError(
            "annotation needs a diagnosis label and/or a corrected mask before it can be submitted"
        )

    annotation.status = AnnotationStatus.SUBMITTED.value
    annotation.submitted_at = datetime.now(timezone.utc)
    db.flush()
    audit_repository.record(
        db, user_id=actor.id, action="annotation_submitted", resource_type="annotation",
        resource_id=str(annotation.id), result="success",
    )
    return annotation


def review(
    db: Session, *, reviewer: User, annotation: Annotation, approve: bool, comment: str | None = None
) -> Annotation:
    if annotation.status != AnnotationStatus.SUBMITTED.value:
        raise InvalidAnnotationStateError("only a SUBMITTED annotation can be reviewed")

    annotation.status = AnnotationStatus.APPROVED.value if approve else AnnotationStatus.REJECTED.value
    annotation.reviewer_id = reviewer.id
    annotation.review_comment = comment
    annotation.reviewed_at = datetime.now(timezone.utc)
    db.flush()
    audit_repository.record(
        db, user_id=reviewer.id, action="annotation_reviewed", resource_type="annotation",
        resource_id=str(annotation.id), result="success",
        event_metadata={"approved": approve, "comment": comment},
    )
    return annotation
