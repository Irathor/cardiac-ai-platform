import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.roles import RoleName
from app.db.session import get_db
from app.models.model_version import ModelVersion
from app.models.user import User
from app.repositories import model_repository
from app.schemas.model import (
    ModelEvaluationOut,
    ModelPromoteRequest,
    ModelReviewRequest,
    ModelVersionOut,
)
from app.services import model_service

router = APIRouter()

_MODEL_VERSION_NOT_FOUND = "Model version not found"

_VIEW_ROLES = (RoleName.ML_ENGINEER, RoleName.MODEL_APPROVER, RoleName.ADMIN)


def _load_model_version(db: Session, model_version_id: uuid.UUID) -> ModelVersion:
    model_version = model_repository.get_by_id(db, model_version_id)
    if model_version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_MODEL_VERSION_NOT_FOUND)
    return model_version


@router.get("/model-versions")
def list_model_versions(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_VIEW_ROLES)),
) -> list[ModelVersionOut]:
    return [ModelVersionOut.model_validate(m) for m in model_repository.list_all(db)]


@router.get("/model-versions/{model_version_id}")
def get_model_version(
    model_version_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_VIEW_ROLES)),
) -> ModelVersionOut:
    return ModelVersionOut.model_validate(_load_model_version(db, model_version_id))


@router.get("/model-versions/{model_version_id}/evaluations")
def list_model_evaluations(
    model_version_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*_VIEW_ROLES)),
) -> list[ModelEvaluationOut]:
    _load_model_version(db, model_version_id)
    return [
        ModelEvaluationOut.model_validate(e)
        for e in model_repository.list_evaluations(db, model_version_id)
    ]


@router.post("/model-versions/{model_version_id}/review")
def review_model_version(
    model_version_id: uuid.UUID,
    payload: ModelReviewRequest,
    db: Session = Depends(get_db),
    approver: User = Depends(require_roles(RoleName.MODEL_APPROVER)),
) -> ModelVersionOut:
    model_version = _load_model_version(db, model_version_id)
    try:
        model_service.review(
            db, approver=approver, model_version=model_version,
            approve=payload.approve, justification=payload.justification,
        )
    except model_service.MissingJustificationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except model_service.InvalidModelStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(model_version)
    return ModelVersionOut.model_validate(model_version)


@router.post("/model-versions/{model_version_id}/promote")
def promote_model_version(
    model_version_id: uuid.UUID,
    payload: ModelPromoteRequest,
    db: Session = Depends(get_db),
    approver: User = Depends(require_roles(RoleName.MODEL_APPROVER)),
) -> ModelVersionOut:
    model_version = _load_model_version(db, model_version_id)
    try:
        model_service.promote(
            db, approver=approver, model_version=model_version, justification=payload.justification
        )
    except model_service.MissingJustificationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except model_service.InvalidModelStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(model_version)
    return ModelVersionOut.model_validate(model_version)
