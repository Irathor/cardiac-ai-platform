import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.biomarker_measurement import BiomarkerMeasurement
from app.models.segmentation import Segmentation


def list_for_series(db: Session, image_series_id: uuid.UUID) -> list[Segmentation]:
    stmt = (
        select(Segmentation)
        .where(Segmentation.image_series_id == image_series_id)
        .order_by(Segmentation.created_at.asc())
    )
    return list(db.execute(stmt).scalars())


def get_by_id(db: Session, segmentation_id: uuid.UUID) -> Segmentation | None:
    stmt = select(Segmentation).where(Segmentation.id == segmentation_id)
    return db.execute(stmt).scalar_one_or_none()


def create(
    db: Session, *, image_series_id: uuid.UUID, created_by: uuid.UUID | None, **fields
) -> Segmentation:
    segmentation = Segmentation(image_series_id=image_series_id, created_by=created_by, **fields)
    db.add(segmentation)
    db.flush()
    return segmentation


def add_measurements(
    db: Session, *, segmentation_id: uuid.UUID, measurements: list[tuple[str, float, str]]
) -> list[BiomarkerMeasurement]:
    rows = [
        BiomarkerMeasurement(segmentation_id=segmentation_id, name=name, value=value, unit=unit)
        for name, value, unit in measurements
    ]
    db.add_all(rows)
    db.flush()
    return rows


def list_measurements(db: Session, segmentation_id: uuid.UUID) -> list[BiomarkerMeasurement]:
    stmt = (
        select(BiomarkerMeasurement)
        .where(BiomarkerMeasurement.segmentation_id == segmentation_id)
        .order_by(BiomarkerMeasurement.name.asc())
    )
    return list(db.execute(stmt).scalars())
