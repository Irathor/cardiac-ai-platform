import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.enums import TrainingModelType
from app.core.roles import RoleName
from app.db.session import get_db
from app.models.dataset_version import DatasetVersion
from app.models.user import User
from app.repositories import dataset_repository, training_repository
from app.schemas.training import TrainingRunOut, TrainingRunRequest
from app.services import training_service
from app.tasks.training_tasks import run_training

router = APIRouter()

_VERSION_NOT_FOUND = "Dataset version not found"
_TRAINING_RUN_NOT_FOUND = "Training run not found"

# ADMIN added alongside ML_ENGINEER (docs/permissions.md) — ADMIN can now
# trigger/view training runs, but still never approves/promotes a model
# (MODEL_APPROVER-only, unchanged — see app.api.v1.models).
_TRAINING_ROLES = (RoleName.ML_ENGINEER, RoleName.ADMIN)


def _load_version(db: Session, dataset_id: uuid.UUID, version_id: uuid.UUID) -> DatasetVersion:
    version = dataset_repository.get_version_by_id(db, version_id)
    if version is None or version.dataset_id != dataset_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_VERSION_NOT_FOUND)
    return version


@router.post(
    "/datasets/{dataset_id}/versions/{version_id}/training-runs", status_code=status.HTTP_202_ACCEPTED
)
def request_training_run(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: TrainingRunRequest | None = None,
    db: Session = Depends(get_db),
    engineer: User = Depends(require_roles(*_TRAINING_ROLES)),
) -> TrainingRunOut:
    version = _load_version(db, dataset_id, version_id)
    model_type = payload.model_type if payload is not None else TrainingModelType.NEAREST_CENTROID
    try:
        run = training_service.create_training_run(
            db, actor=engineer, dataset_version=version, model_type=model_type
        )
    except training_service.DatasetVersionNotLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(run)
    run_training.delay(str(run.id))
    return TrainingRunOut.model_validate(run)


@router.get("/datasets/{dataset_id}/versions/{version_id}/training-runs")
def list_training_runs(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: Session = Depends(get_db),
    engineer: User = Depends(require_roles(*_TRAINING_ROLES)),
) -> list[TrainingRunOut]:
    version = _load_version(db, dataset_id, version_id)
    return [TrainingRunOut.model_validate(r) for r in training_repository.list_for_dataset_version(db, version.id)]


@router.get("/training-runs/{training_run_id}")
def get_training_run(
    training_run_id: uuid.UUID,
    db: Session = Depends(get_db),
    engineer: User = Depends(require_roles(*_TRAINING_ROLES)),
) -> TrainingRunOut:
    run = training_repository.get_by_id(db, training_run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_TRAINING_RUN_NOT_FOUND)
    return TrainingRunOut.model_validate(run)
