import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.image_series import ImageSeries


def list_for_study(db: Session, imaging_study_id: uuid.UUID) -> list[ImageSeries]:
    stmt = (
        select(ImageSeries)
        .where(ImageSeries.imaging_study_id == imaging_study_id)
        .order_by(ImageSeries.created_at.asc())
    )
    return list(db.execute(stmt).scalars())


def get_by_id(db: Session, series_id: uuid.UUID) -> ImageSeries | None:
    stmt = select(ImageSeries).where(ImageSeries.id == series_id)
    return db.execute(stmt).scalar_one_or_none()


def create(db: Session, *, imaging_study_id: uuid.UUID, uploaded_by: uuid.UUID | None, **fields) -> ImageSeries:
    series = ImageSeries(imaging_study_id=imaging_study_id, uploaded_by=uploaded_by, **fields)
    db.add(series)
    db.flush()
    return series
