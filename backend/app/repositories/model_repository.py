import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import ModelVersionStatus
from app.models.model_approval import ModelApproval
from app.models.model_evaluation import ModelEvaluation
from app.models.model_version import ModelVersion


def get_by_id(db: Session, model_version_id: uuid.UUID) -> ModelVersion | None:
    stmt = select(ModelVersion).where(
        ModelVersion.id == model_version_id, ModelVersion.deleted_at.is_(None)
    )
    return db.execute(stmt).scalar_one_or_none()


def list_all(db: Session) -> list[ModelVersion]:
    stmt = (
        select(ModelVersion)
        .where(ModelVersion.deleted_at.is_(None))
        .order_by(ModelVersion.created_at.desc())
    )
    return list(db.execute(stmt).scalars())


def get_production(db: Session, name: str) -> ModelVersion | None:
    stmt = select(ModelVersion).where(
        ModelVersion.name == name,
        ModelVersion.status == ModelVersionStatus.PRODUCTION.value,
        ModelVersion.deleted_at.is_(None),
    )
    return db.execute(stmt).scalar_one_or_none()


def create(db: Session, *, training_run_id: uuid.UUID, created_by: uuid.UUID | None, **fields) -> ModelVersion:
    model_version = ModelVersion(training_run_id=training_run_id, created_by=created_by, **fields)
    db.add(model_version)
    db.flush()
    return model_version


def create_evaluation(db: Session, *, model_version_id: uuid.UUID, **fields) -> ModelEvaluation:
    evaluation = ModelEvaluation(model_version_id=model_version_id, **fields)
    db.add(evaluation)
    db.flush()
    return evaluation


def list_evaluations(db: Session, model_version_id: uuid.UUID) -> list[ModelEvaluation]:
    stmt = select(ModelEvaluation).where(ModelEvaluation.model_version_id == model_version_id)
    return list(db.execute(stmt).scalars())


def create_approval(
    db: Session, *, model_version_id: uuid.UUID, approver_id: uuid.UUID, **fields
) -> ModelApproval:
    approval = ModelApproval(model_version_id=model_version_id, approver_id=approver_id, **fields)
    db.add(approval)
    db.flush()
    return approval


def list_approvals(db: Session, model_version_id: uuid.UUID) -> list[ModelApproval]:
    stmt = (
        select(ModelApproval)
        .where(ModelApproval.model_version_id == model_version_id)
        .order_by(ModelApproval.created_at.desc())
    )
    return list(db.execute(stmt).scalars())
