import uuid
from collections import defaultdict
from datetime import datetime

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


def list_recent_measurements_by_name(
    db: Session, *, since: datetime, limit: int
) -> dict[str, list[float]]:
    """Recent biomarker measurements grouped by `name` (EPIC-7, "Contrato
    técnico" point 2): every `BiomarkerMeasurement` whose owning
    `Segmentation.created_at >= since`, ordered by `Segmentation.created_at`
    descending, with `limit` applied *per biomarker name* — not `limit`
    rows total across every name. Used by drift_service as the "recent"
    sample for the KS test, independent of the base sample computed from a
    DatasetVersion (see drift_service.get_drift_report)."""
    stmt = (
        select(BiomarkerMeasurement.name, BiomarkerMeasurement.value, Segmentation.created_at)
        .join(Segmentation, BiomarkerMeasurement.segmentation_id == Segmentation.id)
        .where(Segmentation.created_at >= since)
        .order_by(Segmentation.created_at.desc())
    )
    by_name: dict[str, list[float]] = defaultdict(list)
    for name, value, _created_at in db.execute(stmt).all():
        if len(by_name[name]) < limit:
            by_name[name].append(value)
    return dict(by_name)
