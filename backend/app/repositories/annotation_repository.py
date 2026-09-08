import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.annotation import Annotation
from app.models.image_series import ImageSeries
from app.models.imaging_study import ImagingStudy
from app.models.segmentation import Segmentation


def get_by_id(db: Session, annotation_id: uuid.UUID) -> Annotation | None:
    stmt = select(Annotation).where(Annotation.id == annotation_id)
    return db.execute(stmt).scalar_one_or_none()


def list_for_segmentation(db: Session, segmentation_id: uuid.UUID) -> list[Annotation]:
    stmt = (
        select(Annotation)
        .where(Annotation.based_on_segmentation_id == segmentation_id)
        .order_by(Annotation.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


def list_for_annotator(db: Session, annotator_id: uuid.UUID) -> list[Annotation]:
    stmt = (
        select(Annotation)
        .where(Annotation.annotator_id == annotator_id)
        .order_by(Annotation.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


def create(
    db: Session, *, based_on_segmentation_id: uuid.UUID, annotator_id: uuid.UUID,
    requested_by: uuid.UUID | None, **fields
) -> Annotation:
    annotation = Annotation(
        based_on_segmentation_id=based_on_segmentation_id, annotator_id=annotator_id,
        requested_by=requested_by, **fields,
    )
    db.add(annotation)
    db.flush()
    return annotation


def get_patient_id(db: Session, annotation: Annotation) -> uuid.UUID | None:
    """Walks annotation -> segmentation -> series -> study -> patient. Used
    to reuse the existing patient-visibility check (see
    app.services.study_service.get_study_for_viewer) for annotation review."""
    stmt = (
        select(ImagingStudy.patient_id)
        .join(ImageSeries, ImageSeries.imaging_study_id == ImagingStudy.id)
        .join(Segmentation, Segmentation.image_series_id == ImageSeries.id)
        .where(Segmentation.id == annotation.based_on_segmentation_id)
    )
    return db.execute(stmt).scalar_one_or_none()


def get_imaging_study(db: Session, annotation: Annotation) -> ImagingStudy | None:
    """Same walk as get_patient_id, but returns the ImagingStudy itself — used
    by training to compute the same feature set live inference uses (see
    app.services.analysis_service.collect_features, which needs a full
    ImagingStudy with paired ED/ES series)."""
    stmt = (
        select(ImagingStudy)
        .join(ImageSeries, ImageSeries.imaging_study_id == ImagingStudy.id)
        .join(Segmentation, Segmentation.image_series_id == ImageSeries.id)
        .where(Segmentation.id == annotation.based_on_segmentation_id)
    )
    return db.execute(stmt).scalar_one_or_none()
