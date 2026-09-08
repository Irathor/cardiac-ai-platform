import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.enums import DatasetSplit
from app.core.roles import RoleName
from app.db.session import get_db
from app.models.dataset import Dataset
from app.models.dataset_version import DatasetVersion
from app.models.user import User
from app.repositories import annotation_repository, dataset_repository
from app.schemas.dataset import (
    DatasetCaseCreateRequest,
    DatasetCaseOut,
    DatasetCreateRequest,
    DatasetOut,
    DatasetVersionOut,
)
from app.services import dataset_service

router = APIRouter()

_DATASET_NOT_FOUND = "Dataset not found"
_VERSION_NOT_FOUND = "Dataset version not found"
_ANNOTATION_NOT_FOUND = "Annotation not found"

_ALLOWED_SPLITS = {s.value for s in DatasetSplit}


def _load_dataset(db: Session, dataset_id: uuid.UUID) -> Dataset:
    dataset = dataset_repository.get_by_id(db, dataset_id)
    if dataset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_DATASET_NOT_FOUND)
    return dataset


def _load_version(db: Session, dataset_id: uuid.UUID, version_id: uuid.UUID) -> DatasetVersion:
    version = dataset_repository.get_version_by_id(db, version_id)
    if version is None or version.dataset_id != dataset_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_VERSION_NOT_FOUND)
    return version


@router.post("/datasets", status_code=status.HTTP_201_CREATED)
def create_dataset(
    payload: DatasetCreateRequest,
    db: Session = Depends(get_db),
    engineer: User = Depends(require_roles(RoleName.ML_ENGINEER)),
) -> DatasetOut:
    dataset = dataset_service.create_dataset(db, actor=engineer, **payload.model_dump())
    db.commit()
    db.refresh(dataset)
    return DatasetOut.model_validate(dataset)


@router.get("/datasets")
def list_datasets(
    db: Session = Depends(get_db),
    engineer: User = Depends(require_roles(RoleName.ML_ENGINEER)),
) -> list[DatasetOut]:
    return [DatasetOut.model_validate(d) for d in dataset_repository.list_datasets(db)]


@router.get("/datasets/{dataset_id}")
def get_dataset(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    engineer: User = Depends(require_roles(RoleName.ML_ENGINEER)),
) -> DatasetOut:
    return DatasetOut.model_validate(_load_dataset(db, dataset_id))


@router.post("/datasets/{dataset_id}/versions", status_code=status.HTTP_201_CREATED)
def create_dataset_version(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    engineer: User = Depends(require_roles(RoleName.ML_ENGINEER)),
) -> DatasetVersionOut:
    dataset = _load_dataset(db, dataset_id)
    version = dataset_service.create_version(db, actor=engineer, dataset=dataset)
    db.commit()
    db.refresh(version)
    return DatasetVersionOut.model_validate(version)


@router.get("/datasets/{dataset_id}/versions")
def list_dataset_versions(
    dataset_id: uuid.UUID,
    db: Session = Depends(get_db),
    engineer: User = Depends(require_roles(RoleName.ML_ENGINEER)),
) -> list[DatasetVersionOut]:
    _load_dataset(db, dataset_id)
    return [DatasetVersionOut.model_validate(v) for v in dataset_repository.list_versions(db, dataset_id)]


@router.post("/datasets/{dataset_id}/versions/{version_id}/cases", status_code=status.HTTP_201_CREATED)
def add_dataset_case(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: DatasetCaseCreateRequest,
    db: Session = Depends(get_db),
    engineer: User = Depends(require_roles(RoleName.ML_ENGINEER)),
) -> DatasetCaseOut:
    version = _load_version(db, dataset_id, version_id)
    if payload.split not in _ALLOWED_SPLITS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"split must be one of {sorted(_ALLOWED_SPLITS)}",
        )
    annotation = annotation_repository.get_by_id(db, payload.annotation_id)
    if annotation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ANNOTATION_NOT_FOUND)

    try:
        case = dataset_service.add_case(
            db, actor=engineer, version=version, annotation=annotation, split=payload.split
        )
    except dataset_service.AnnotationNotApprovedError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    except dataset_service.DatasetVersionLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except dataset_service.PatientSplitConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(case)
    return DatasetCaseOut.model_validate(case)


@router.get("/datasets/{dataset_id}/versions/{version_id}/cases")
def list_dataset_cases(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    engineer: User = Depends(require_roles(RoleName.ML_ENGINEER)),
) -> list[DatasetCaseOut]:
    version = _load_version(db, dataset_id, version_id)
    return [DatasetCaseOut.model_validate(c) for c in dataset_repository.list_cases(db, version.id)]


@router.post("/datasets/{dataset_id}/versions/{version_id}/lock")
def lock_dataset_version(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    engineer: User = Depends(require_roles(RoleName.ML_ENGINEER)),
) -> DatasetVersionOut:
    version = _load_version(db, dataset_id, version_id)
    try:
        version = dataset_service.lock_version(db, actor=engineer, version=version)
    except dataset_service.DatasetVersionLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except dataset_service.EmptyDatasetVersionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    db.commit()
    db.refresh(version)
    return DatasetVersionOut.model_validate(version)
