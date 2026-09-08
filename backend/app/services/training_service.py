""""Smoke training" orchestration (see ml.cardiac_ai_ml.training and
docs/phases.md). `create_training_run` (request/response path) only ever
writes a QUEUED row and hands off to Celery — same split as
analysis_service.create_analysis/execute_analysis, and for the same reason
(docs/architecture.md: heavyweight/ml work never runs inside an HTTP
request). `execute_training` is only ever called from
app.tasks.training_tasks, i.e. from the Celery worker.
"""
import uuid
from datetime import datetime, timezone

import mlflow
from cardiac_ai_ml.classification import DiagnosisClass
from cardiac_ai_ml.training import EmptyTrainingSetError, MissingClassError, TrainingCase, evaluate, fit_nearest_centroid
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import DatasetVersionStatus, ModelVersionStatus, TrainingRunStatus
from app.core.model_registry import MODEL_NAME
from app.models.dataset_version import DatasetVersion
from app.models.training_run import TrainingRun
from app.models.user import User
from app.repositories import annotation_repository, audit_repository, dataset_repository, model_repository, training_repository
from app.services import analysis_service

ALL_DIAGNOSIS_LABELS = {d.value for d in DiagnosisClass}


class DatasetVersionNotLockedError(ValueError):
    pass


def create_training_run(db: Session, *, actor: User, dataset_version: DatasetVersion) -> TrainingRun:
    if dataset_version.status != DatasetVersionStatus.LOCKED.value:
        raise DatasetVersionNotLockedError("can only train on a LOCKED dataset version")

    run = training_repository.create(
        db, dataset_version_id=dataset_version.id, requested_by=actor.id,
        status=TrainingRunStatus.QUEUED.value,
    )
    audit_repository.record(
        db, user_id=actor.id, action="training_run_requested", resource_type="training_run",
        resource_id=str(run.id), result="success",
        event_metadata={"dataset_version_id": str(dataset_version.id)},
    )
    return run


def _cases_for_split(db: Session, dataset_version_id: uuid.UUID, split: str) -> tuple[list[TrainingCase], int]:
    """Returns (usable cases, excluded count). A case is excluded when its
    underlying study doesn't have a usable ED+ES pair — the exact same
    requirement live inference has (see analysis_service.collect_features) —
    so training and inference are always evaluated on the same feature
    space, never a training-only shortcut."""
    all_cases = [c for c in dataset_repository.list_cases(db, dataset_version_id) if c.split == split]
    usable: list[TrainingCase] = []
    excluded = 0
    for case in all_cases:
        annotation = annotation_repository.get_by_id(db, case.annotation_id)
        study = annotation_repository.get_imaging_study(db, annotation) if annotation else None
        if annotation is None or annotation.diagnosis_label is None or study is None:
            excluded += 1
            continue
        try:
            features = analysis_service.collect_features(db, study)
        except analysis_service.MissingPhaseDataError:
            excluded += 1
            continue
        usable.append(TrainingCase(features=features, label=annotation.diagnosis_label))
    return usable, excluded


def execute_training(db: Session, *, training_run_id: uuid.UUID) -> None:
    """Runs entirely inside the Celery worker — never call from an HTTP
    request handler."""
    run = training_repository.get_by_id(db, training_run_id)
    if run is None:
        return

    run.status = TrainingRunStatus.RUNNING.value
    run.started_at = datetime.now(timezone.utc)
    db.flush()

    try:
        train_cases, train_excluded = _cases_for_split(db, run.dataset_version_id, "TRAIN")
        test_cases, test_excluded = _cases_for_split(db, run.dataset_version_id, "TEST")

        prototypes = fit_nearest_centroid(train_cases, ALL_DIAGNOSIS_LABELS)
        result = evaluate(prototypes, test_cases)

        settings = get_settings()
        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment(MODEL_NAME)
        with mlflow.start_run(run_name=f"training-run-{run.id}") as mlflow_run:
            mlflow.log_param("dataset_version_id", str(run.dataset_version_id))
            mlflow.log_param("algorithm", "nearest-centroid")
            mlflow.log_param("train_case_count", len(train_cases))
            mlflow.log_param("train_excluded_count", train_excluded)
            mlflow.log_metric("test_accuracy", result.accuracy)
            mlflow.log_dict(prototypes, "prototypes.json")
            mlflow_run_id = mlflow_run.info.run_id
            mlflow_model_uri = f"{mlflow_run.info.artifact_uri}/prototypes.json"

        model_version = model_repository.create(
            db, training_run_id=run.id, created_by=run.requested_by,
            name=MODEL_NAME, mlflow_run_id=mlflow_run_id, mlflow_model_uri=mlflow_model_uri,
            prototypes=prototypes, status=ModelVersionStatus.PENDING_REVIEW.value,
        )
        model_repository.create_evaluation(
            db, model_version_id=model_version.id, split="TEST",
            accuracy=result.accuracy,
            metrics={
                "case_count": result.case_count,
                "correct_count": result.correct_count,
                "per_class_accuracy": result.per_class_accuracy,
            },
        )

        run.status = TrainingRunStatus.COMPLETED.value
        run.metrics = {
            "test_accuracy": result.accuracy,
            "train_case_count": len(train_cases),
            "train_excluded_count": train_excluded,
            "test_case_count": len(test_cases),
            "test_excluded_count": test_excluded,
        }
        run.mlflow_run_id = mlflow_run_id
        audit_repository.record(
            db, user_id=run.requested_by, action="training_run_completed", resource_type="training_run",
            resource_id=str(run.id), result="success",
            event_metadata={"model_version_id": str(model_version.id), "test_accuracy": result.accuracy},
        )
    except (EmptyTrainingSetError, MissingClassError) as exc:
        run.status = TrainingRunStatus.FAILED.value
        run.error_message = str(exc)
        audit_repository.record(
            db, user_id=run.requested_by, action="training_run_failed", resource_type="training_run",
            resource_id=str(run.id), result="failure", event_metadata={"error": str(exc)},
        )
    except Exception as exc:  # noqa: BLE001 — a training run must always resolve to
        # COMPLETED or FAILED, never crash the worker or leave RUNNING forever,
        # regardless of what kind of error (mlflow connectivity, a bad artifact
        # write, ...) actually caused it.
        run.status = TrainingRunStatus.FAILED.value
        run.error_message = f"{type(exc).__name__}: {exc}"
        audit_repository.record(
            db, user_id=run.requested_by, action="training_run_failed", resource_type="training_run",
            resource_id=str(run.id), result="failure", event_metadata={"error": run.error_message},
        )
    run.completed_at = datetime.now(timezone.utc)
    db.flush()
