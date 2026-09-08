"""One-off backfill: ingests the real U-Net/CNN3D metrics JSON files already
produced by the standalone ml/ training scripts (run directly against the
host GPU during development, not through app.services.training_service.
execute_dl_training) into TrainingRun/ModelVersion/ModelEvaluation rows plus
a real MLflow run each — so /admin/training has real history to browse
without waiting for another real 25-40 minute GPU run.

Every number recorded here is read straight from the real JSON files under
settings.data_root (see docs/dl-training-runner.md) — nothing is
recomputed, estimated, or fabricated; this script only records that the
run already happened and where its real output lives. `TrainingRun.metrics`
is explicitly annotated as backfilled so it's never confused with a run
that actually went through the runner service.

Usage: python -m app.scripts.backfill_dl_results
"""
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mlflow

from app.core.config import get_settings
from app.core.enums import ModelVersionStatus, TrainingModelType, TrainingRunStatus
from app.core.model_registry import MODEL_NAME_CNN3D, MODEL_NAME_UNET
from app.db.session import get_session_factory
from app.repositories import model_repository, training_repository, user_repository


def _total_seconds(history: list[dict]) -> float:
    return sum(entry.get("epoch_time_s", 0.0) for entry in history)


def _record_run_and_version(
    db,
    *,
    model_type: TrainingModelType,
    model_name: str,
    requested_by: uuid.UUID | None,
    duration_s: float,
    headline_metrics: dict,
    full_metrics: dict,
    accuracy: float | None,
    weights_path: Path,
) -> None:
    completed_at = datetime.now(timezone.utc)
    started_at = completed_at - timedelta(seconds=duration_s)

    run = training_repository.create(
        db, dataset_version_id=None, requested_by=requested_by,
        status=TrainingRunStatus.COMPLETED.value, model_type=model_type.value,
    )
    run.started_at = started_at
    run.completed_at = completed_at
    run.metrics = {
        "backfilled": True,
        "note": "Real GPU run executed standalone via ml/scripts; ingested after the fact — see app/scripts/backfill_dl_results.py.",
        **headline_metrics,
    }
    db.flush()

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_experiment(model_name)
    with mlflow.start_run(run_name=f"backfill-training-run-{run.id}") as mlflow_run:
        mlflow.log_param("model_type", model_type.value)
        mlflow.log_param("backfilled", True)
        for key, value in headline_metrics.items():
            mlflow.log_metric(key, value)
        mlflow.log_dict(full_metrics, "metrics.json")
        if weights_path.exists():
            mlflow.log_artifact(str(weights_path))
        mlflow_run_id = mlflow_run.info.run_id
        mlflow_model_uri = f"{mlflow_run.info.artifact_uri}/metrics.json"

    model_version = model_repository.create(
        db, training_run_id=run.id, created_by=requested_by,
        name=model_name, mlflow_run_id=mlflow_run_id, mlflow_model_uri=mlflow_model_uri,
        prototypes=None, status=ModelVersionStatus.PENDING_REVIEW.value,
    )
    model_version.created_at = completed_at
    model_repository.create_evaluation(
        db, model_version_id=model_version.id, split="TEST", accuracy=accuracy, metrics=full_metrics,
    )
    run.mlflow_run_id = mlflow_run_id
    db.flush()
    print(f"backfilled {model_name}: training run {run.id} -> model version {model_version.id}")


def _backfill_unet(db, data_root: Path, requested_by: uuid.UUID | None) -> None:
    metrics_path = data_root / "models" / "unet2d.metrics.json"
    if not metrics_path.exists():
        print(f"skip U-Net: {metrics_path} not found", file=sys.stderr)
        return
    metrics = json.loads(metrics_path.read_text())
    _record_run_and_version(
        db,
        model_type=TrainingModelType.UNET_SEGMENTATION,
        model_name=MODEL_NAME_UNET,
        requested_by=requested_by,
        duration_s=_total_seconds(metrics.get("history", [])),
        headline_metrics={"test_mean_dice_foreground": metrics["test"]["mean_dice_foreground"]},
        full_metrics=metrics,
        accuracy=metrics["test"]["mean_dice_foreground"],
        weights_path=data_root / "models" / "unet2d.pt",
    )


def _backfill_cnn3d(db, data_root: Path, requested_by: uuid.UUID | None) -> None:
    cnn3d_dir = data_root / "models" / "cnn3d"
    cv_path = cnn3d_dir / "cross_validation.json"
    if not cv_path.exists():
        print(f"skip CNN3D: {cv_path} not found", file=sys.stderr)
        return

    cross_validation = json.loads(cv_path.read_text())
    final_model_training = json.loads((cnn3d_dir / "final_model_training.json").read_text())
    external_test = json.loads((cnn3d_dir / "external_test.json").read_text())
    full_metrics = {
        "cross_validation": cross_validation,
        "final_model_training": final_model_training,
        "external_test": external_test,
    }
    ensemble_path = cnn3d_dir / "ensemble_external_test.json"
    if ensemble_path.exists():
        full_metrics["ensemble_external_test"] = json.loads(ensemble_path.read_text())

    duration_s = _total_seconds(final_model_training.get("history", []))
    for fold in cross_validation.get("folds", []):
        duration_s += _total_seconds(fold.get("training", {}).get("history", []))

    _record_run_and_version(
        db,
        model_type=TrainingModelType.CNN3D_CLASSIFICATION,
        model_name=MODEL_NAME_CNN3D,
        requested_by=requested_by,
        duration_s=duration_s,
        headline_metrics={
            "cv_mean_accuracy": cross_validation["mean_accuracy"],
            "external_test_accuracy": external_test["accuracy"],
        },
        full_metrics=full_metrics,
        accuracy=external_test["accuracy"],
        weights_path=cnn3d_dir / "cnn3d.pt",
    )


def main() -> None:
    settings = get_settings()
    if settings.environment == "production":
        print("Refusing to backfill demo data: ENVIRONMENT=production", file=sys.stderr)
        sys.exit(1)

    session_factory = get_session_factory()
    db = session_factory()
    try:
        ml_engineer = user_repository.get_by_email(db, "ml_engineer@demo.cardiacai-test.dev")
        requested_by = ml_engineer.id if ml_engineer is not None else None

        data_root = Path(settings.data_root)
        _backfill_unet(db, data_root, requested_by)
        _backfill_cnn3d(db, data_root, requested_by)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
