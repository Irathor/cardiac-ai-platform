import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.dataset_case import DatasetCase
from app.models.dataset_version import DatasetVersion


def list_datasets(db: Session) -> list[Dataset]:
    return list(db.execute(select(Dataset).order_by(Dataset.name)).scalars())


def get_by_id(db: Session, dataset_id: uuid.UUID) -> Dataset | None:
    stmt = select(Dataset).where(Dataset.id == dataset_id)
    return db.execute(stmt).scalar_one_or_none()


def create(db: Session, *, created_by: uuid.UUID | None, **fields) -> Dataset:
    dataset = Dataset(created_by=created_by, **fields)
    db.add(dataset)
    db.flush()
    return dataset


def get_version_by_id(db: Session, version_id: uuid.UUID) -> DatasetVersion | None:
    stmt = select(DatasetVersion).where(DatasetVersion.id == version_id)
    return db.execute(stmt).scalar_one_or_none()


def list_versions(db: Session, dataset_id: uuid.UUID) -> list[DatasetVersion]:
    stmt = (
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.version_number.desc())
    )
    return list(db.execute(stmt).scalars())


def next_version_number(db: Session, dataset_id: uuid.UUID) -> int:
    stmt = select(func.max(DatasetVersion.version_number)).where(DatasetVersion.dataset_id == dataset_id)
    current_max = db.execute(stmt).scalar_one()
    return (current_max or 0) + 1


def create_version(db: Session, *, dataset_id: uuid.UUID, created_by: uuid.UUID | None, **fields) -> DatasetVersion:
    version = DatasetVersion(dataset_id=dataset_id, created_by=created_by, **fields)
    db.add(version)
    db.flush()
    return version


def list_cases(db: Session, dataset_version_id: uuid.UUID) -> list[DatasetCase]:
    stmt = (
        select(DatasetCase)
        .where(DatasetCase.dataset_version_id == dataset_version_id)
        .order_by(DatasetCase.created_at.asc())
    )
    return list(db.execute(stmt).scalars())


def get_case_for_patient(db: Session, *, dataset_version_id: uuid.UUID, patient_id: uuid.UUID) -> DatasetCase | None:
    stmt = select(DatasetCase).where(
        DatasetCase.dataset_version_id == dataset_version_id, DatasetCase.patient_id == patient_id
    ).limit(1)
    return db.execute(stmt).scalar_one_or_none()


def create_case(db: Session, **fields) -> DatasetCase:
    case = DatasetCase(**fields)
    db.add(case)
    db.flush()
    return case
