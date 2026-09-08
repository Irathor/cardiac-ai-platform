import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.training_run import TrainingRun


def get_by_id(db: Session, training_run_id: uuid.UUID) -> TrainingRun | None:
    stmt = select(TrainingRun).where(TrainingRun.id == training_run_id)
    return db.execute(stmt).scalar_one_or_none()


def list_for_dataset_version(db: Session, dataset_version_id: uuid.UUID) -> list[TrainingRun]:
    stmt = (
        select(TrainingRun)
        .where(TrainingRun.dataset_version_id == dataset_version_id)
        .order_by(TrainingRun.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


def create(db: Session, *, dataset_version_id: uuid.UUID, requested_by: uuid.UUID | None, **fields) -> TrainingRun:
    run = TrainingRun(dataset_version_id=dataset_version_id, requested_by=requested_by, **fields)
    db.add(run)
    db.flush()
    return run
