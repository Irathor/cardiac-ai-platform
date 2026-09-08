""""Smoke training" orchestration (see ml.cardiac_ai_ml.training and
docs/phases.md). `create_training_run` (request/response path) only ever
writes a QUEUED row and hands off to Celery — same split as
analysis_service.create_analysis/execute_analysis, and for the same reason
(docs/architecture.md: heavyweight/ml work never runs inside an HTTP
request). `execute_training` is only ever called from
app.tasks.training_tasks, i.e. from the Celery worker.
"""
import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import mlflow
from cardiac_ai_ml.classification import DiagnosisClass
from cardiac_ai_ml.training import EmptyTrainingSetError, MissingClassError, TrainingCase, evaluate, fit_nearest_centroid
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import DatasetVersionStatus, ModelVersionStatus, TrainingModelType, TrainingRunStatus
from app.core.model_registry import MODEL_NAME, MODEL_NAME_CNN3D, MODEL_NAME_UNET
from app.models.dataset_version import DatasetVersion
from app.models.training_run import TrainingRun
from app.models.user import User
from app.repositories import annotation_repository, audit_repository, dataset_repository, model_repository, training_repository
from app.services import analysis_service

ALL_DIAGNOSIS_LABELS = {d.value for d in DiagnosisClass}

# How long execute_dl_training will poll the host runner before giving up —
# generous enough for a genuine ~60-epoch GPU run, but finite: a training run
# must always resolve to COMPLETED or FAILED, never stay RUNNING forever.
_DL_POLL_INTERVAL_S = 10
_DL_TIMEOUT_S = 90 * 60


class DatasetVersionNotLockedError(ValueError):
    pass


class TrainingRunnerError(RuntimeError):
    """Raised for anything that stops execute_dl_training from reaching a
    COMPLETED job on the host runner — unreachable service, a FAILED job, or
    a timeout. Always caught by execute_dl_training's own broad handler."""


def create_training_run(
    db: Session, *, actor: User, dataset_version: DatasetVersion | None,
    model_type: TrainingModelType = TrainingModelType.NEAREST_CENTROID,
) -> TrainingRun:
    """dataset_version is required (and must be LOCKED) only for
    NEAREST_CENTROID — U-Net/CNN3D train against real ACDC image data on
    disk instead (see docs/dl-training-runner.md), a genuinely different
    pipeline from the tabular-biomarker DatasetVersion mechanism. The API
    route still always supplies a dataset_version (kept in the URL for
    audit/consistency, per the plan), this stays optional here so the
    service itself doesn't assume it."""
    if model_type == TrainingModelType.NEAREST_CENTROID:
        if dataset_version is None or dataset_version.status != DatasetVersionStatus.LOCKED.value:
            raise DatasetVersionNotLockedError("can only train on a LOCKED dataset version")

    run = training_repository.create(
        db, dataset_version_id=dataset_version.id if dataset_version is not None else None,
        requested_by=actor.id, status=TrainingRunStatus.QUEUED.value, model_type=model_type.value,
    )
    audit_repository.record(
        db, user_id=actor.id, action="training_run_requested", resource_type="training_run",
        resource_id=str(run.id), result="success",
        event_metadata={
            "dataset_version_id": str(dataset_version.id) if dataset_version is not None else None,
            "model_type": model_type.value,
        },
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


def _load_dl_metrics(data_root: str, model_type: str, result_path: str) -> tuple[dict, float | None, str, Path]:
    """Reads the runner's real metrics JSON straight off the shared /data
    mount (see settings.data_root) — the worker and the host runner both
    have it mounted, so the file never needs to travel over HTTP. Returns
    (metrics dict to persist, headline accuracy scalar, ModelVersion name,
    path to the trained weights file to log as an MLflow artifact)."""
    full_path = Path(data_root) / result_path

    if model_type == TrainingModelType.UNET_SEGMENTATION.value:
        metrics = json.loads(full_path.read_text())
        accuracy = metrics.get("test", {}).get("mean_dice_foreground")
        # train_segmentation.py writes "<output-stem>.metrics.json" next to
        # "<output-stem>.pt" (Path.with_suffix(".metrics.json") on the .pt
        # path) — invert that to find the weights file.
        weights_path = full_path.with_suffix("").with_suffix(".pt")
        return metrics, accuracy, MODEL_NAME_UNET, weights_path

    if model_type == TrainingModelType.CNN3D_CLASSIFICATION.value:
        cross_validation = json.loads((full_path / "cross_validation.json").read_text())
        final_model_training = json.loads((full_path / "final_model_training.json").read_text())
        external_test = json.loads((full_path / "external_test.json").read_text())
        metrics = {
            "cross_validation": cross_validation,
            "final_model_training": final_model_training,
            "external_test": external_test,
        }
        # Present only when the training script ensembles the k CV fold
        # models on the external test set (see train_classification.py) —
        # older artifacts predating that feature won't have it.
        ensemble_path = full_path / "ensemble_external_test.json"
        if ensemble_path.exists():
            metrics["ensemble_external_test"] = json.loads(ensemble_path.read_text())
        return metrics, external_test.get("accuracy"), MODEL_NAME_CNN3D, full_path / "cnn3d.pt"

    raise TrainingRunnerError(f"unknown DL model_type {model_type!r}")


def execute_dl_training(db: Session, *, training_run_id: uuid.UUID) -> None:
    """Runs entirely inside the Celery worker, same as execute_training —
    but the actual training happens on the host GPU via
    ml/scripts/training_runner_service.py (see docs/dl-training-runner.md),
    reached over HTTP. This function only launches the job, polls it, and
    persists whatever real metrics JSON it produced; it blocks the worker
    task for the training's duration, which is fine — see
    app.tasks.training_tasks, Celery's own timeout isn't in play here."""
    run = training_repository.get_by_id(db, training_run_id)
    if run is None:
        return

    run.status = TrainingRunStatus.RUNNING.value
    run.started_at = datetime.now(timezone.utc)
    db.flush()

    settings = get_settings()
    try:
        job_response = httpx.post(
            f"{settings.training_runner_url}/jobs", json={"model_type": run.model_type}, timeout=30.0,
        )
        job_response.raise_for_status()
        job_id = job_response.json()["job_id"]

        deadline = time.monotonic() + _DL_TIMEOUT_S
        job_status: dict = {}
        while True:
            if time.monotonic() > deadline:
                raise TrainingRunnerError(
                    f"training runner job {job_id} did not finish within {_DL_TIMEOUT_S}s"
                )
            status_response = httpx.get(f"{settings.training_runner_url}/jobs/{job_id}", timeout=30.0)
            status_response.raise_for_status()
            job_status = status_response.json()
            if job_status["status"] in (TrainingRunStatus.COMPLETED.value, TrainingRunStatus.FAILED.value):
                break
            time.sleep(_DL_POLL_INTERVAL_S)

        if job_status["status"] == TrainingRunStatus.FAILED.value:
            raise TrainingRunnerError(job_status.get("error") or "training runner job failed with no error detail")

        metrics, accuracy, model_name, weights_path = _load_dl_metrics(
            settings.data_root, run.model_type, job_status["result_path"]
        )

        mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
        mlflow.set_experiment(model_name)
        with mlflow.start_run(run_name=f"training-run-{run.id}") as mlflow_run:
            mlflow.log_param("model_type", run.model_type)
            mlflow.log_param("runner_job_id", job_id)
            mlflow.log_dict(metrics, "metrics.json")
            if weights_path.exists():
                mlflow.log_artifact(str(weights_path))
            mlflow_run_id = mlflow_run.info.run_id
            mlflow_model_uri = f"{mlflow_run.info.artifact_uri}/metrics.json"

        model_version = model_repository.create(
            db, training_run_id=run.id, created_by=run.requested_by,
            name=model_name, mlflow_run_id=mlflow_run_id, mlflow_model_uri=mlflow_model_uri,
            prototypes=None, status=ModelVersionStatus.PENDING_REVIEW.value,
        )
        model_repository.create_evaluation(
            db, model_version_id=model_version.id, split="TEST", accuracy=accuracy, metrics=metrics,
        )

        run.status = TrainingRunStatus.COMPLETED.value
        run.metrics = {"runner_job_id": job_id, "result_path": job_status["result_path"]}
        run.mlflow_run_id = mlflow_run_id
        audit_repository.record(
            db, user_id=run.requested_by, action="training_run_completed", resource_type="training_run",
            resource_id=str(run.id), result="success",
            event_metadata={"model_version_id": str(model_version.id), "model_type": run.model_type},
        )
    except Exception as exc:  # noqa: BLE001 — same contract as execute_training:
        # whatever went wrong (runner unreachable, a FAILED job, a timeout, a
        # malformed metrics file, mlflow connectivity), this run must resolve
        # to FAILED with a clear message, never crash the worker or hang in RUNNING.
        run.status = TrainingRunStatus.FAILED.value
        run.error_message = f"{type(exc).__name__}: {exc}"
        audit_repository.record(
            db, user_id=run.requested_by, action="training_run_failed", resource_type="training_run",
            resource_id=str(run.id), result="failure", event_metadata={"error": run.error_message},
        )
    run.completed_at = datetime.now(timezone.utc)
    db.flush()
