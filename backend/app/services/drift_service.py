"""Drift detection over recent biomarkers/predictions vs. a training-time
base (see docs/epics/EPIC-7-deteccion-drift.md, "Contrato técnico").

Two independent comparisons, both read-only over data that already exists —
this module never trains, retrains, or alerts, it only computes and reports
(see the Epic's "Fuera de alcance"):

1. **Biomarker drift** (continuous, per `BiomarkerMeasurement.name`):
   two-sample Kolmogorov-Smirnov test (`scipy.stats.ks_2samp`) between
   recent measurements and the base population derived from the
   `DatasetVersion` (LOCKED) that trained the PRODUCTION model's
   `TrainingRun` — omitted entirely for a model type that doesn't consume a
   `DatasetVersion` (U-Net/CNN3D, see `_biomarker_report`).
2. **Prediction drift** (categorical): Population Stability Index between
   recent `AIAnalysis.predicted_class` and a base window anchored to the
   model version's most recent promotion `AuditEvent`.

`scipy`/`numpy` come in transitively through `cardiac-ai-ml` (already a
backend dependency, see backend/pyproject.toml) — no new dependency added.
"""
import math
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cardiac_ai_ml.classification import DiagnosisClass
from scipy.stats import ks_2samp
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import AnalysisStatus, ModelVersionStatus
from app.core.metrics import BIOMARKER_DRIFT_KS_STATISTIC, BIOMARKER_DRIFT_PVALUE, PREDICTION_DRIFT_PSI
from app.models.ai_analysis import AIAnalysis
from app.models.model_version import ModelVersion
from app.repositories import annotation_repository, audit_repository, dataset_repository, image_series_repository, segmentation_repository

ALL_DIAGNOSIS_LABELS = {d.value for d in DiagnosisClass}

# Constants (EPIC-7 "Contrato técnico" point 3) — not a decision grande, Tali
# can tune these without asking, per "Regla de autonomía".
MIN_SAMPLE_SIZE = 30
RECENT_WINDOW_MAX_DAYS = 30
RECENT_WINDOW_MAX_ROWS = 100
BASE_PREDICTION_WINDOW_MAX_DAYS = 30
BASE_PREDICTION_WINDOW_MAX_ROWS = 100
KS_P_VALUE_THRESHOLD = 0.05
PSI_MODERATE_THRESHOLD = 0.1
PSI_SIGNIFICANT_THRESHOLD = 0.2
_PSI_EPSILON = 1e-4
_CACHE_TTL_SECONDS = 300


class ModelNotInProductionError(ValueError):
    pass


@dataclass
class BiomarkerDriftResult:
    biomarker_name: str
    ks_statistic: float | None
    p_value: float | None
    base_sample_size: int
    recent_sample_size: int
    drift_detected: bool
    skipped_reason: str | None  # set <=> the other numeric fields are None


@dataclass
class PredictionDriftResult:
    psi: float | None
    base_sample_size: int
    recent_sample_size: int
    severity: str  # "NONE" | "MODERATE" | "SIGNIFICANT"
    drift_detected: bool  # severity != "NONE"
    skipped_reason: str | None


@dataclass
class ModelDriftReport:
    model_version_id: uuid.UUID
    evaluated_at: datetime
    biomarkers: list[BiomarkerDriftResult]
    biomarkers_skipped_reason: str | None
    prediction: PredictionDriftResult


# In-memory cache (module-level, per-process — EPIC-7 point 5): repeated
# calls to GET /drift for the same model_version_id within _CACHE_TTL_SECONDS
# don't re-run the DatasetCase -> study -> series -> segmentation traversal
# or re-touch the DB. Keyed by model_version_id; value is (computed_at, report).
_cache: dict[uuid.UUID, tuple[datetime, ModelDriftReport]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _biomarker_base_pool(db: Session, dataset_version_id: uuid.UUID) -> dict[str, list[float]]:
    """Base biomarker population for a LOCKED DatasetVersion, walked via the
    exact same path training already uses (EPIC-7 point 1) so drift never
    becomes a second source of truth for "how a DatasetCase's data is
    reached": `dataset_repository.list_cases` ->
    `annotation_repository.get_by_id`/`get_imaging_study` ->
    `image_series_repository.list_for_study` ->
    `segmentation_repository.list_for_series` (latest segmentation wins,
    same "latest wins" criterion as
    `analysis_service._latest_segmentation_biomarkers`) ->
    `segmentation_repository.list_measurements`. All splits (TRAIN +
    VALIDATION + TEST) are included — deriva measures the full population
    the model was calibrated/evaluated on, not just the fit split."""
    pool: dict[str, list[float]] = {}
    for case in dataset_repository.list_cases(db, dataset_version_id):
        annotation = annotation_repository.get_by_id(db, case.annotation_id)
        if annotation is None:
            continue
        study = annotation_repository.get_imaging_study(db, annotation)
        if study is None:
            continue
        for series in image_series_repository.list_for_study(db, study.id):
            segs = segmentation_repository.list_for_series(db, series.id)
            if not segs:
                continue
            latest = segs[-1]
            for measurement in segmentation_repository.list_measurements(db, latest.id):
                pool.setdefault(measurement.name, []).append(measurement.value)
    return pool


def _ks_result(name: str, base_values: list[float], recent_values: list[float]) -> BiomarkerDriftResult:
    base_n, recent_n = len(base_values), len(recent_values)
    if base_n < MIN_SAMPLE_SIZE or recent_n < MIN_SAMPLE_SIZE:
        return BiomarkerDriftResult(
            biomarker_name=name, ks_statistic=None, p_value=None,
            base_sample_size=base_n, recent_sample_size=recent_n, drift_detected=False,
            skipped_reason=(
                f"insufficient samples for a KS test (base={base_n}, recent={recent_n}, "
                f"minimum required={MIN_SAMPLE_SIZE} each)"
            ),
        )
    stat_result = ks_2samp(recent_values, base_values)
    ks_statistic = float(stat_result.statistic)
    p_value = float(stat_result.pvalue)
    return BiomarkerDriftResult(
        biomarker_name=name, ks_statistic=ks_statistic, p_value=p_value,
        base_sample_size=base_n, recent_sample_size=recent_n,
        drift_detected=p_value < KS_P_VALUE_THRESHOLD, skipped_reason=None,
    )


def _biomarker_report(
    db: Session, *, model_version: ModelVersion
) -> tuple[list[BiomarkerDriftResult], str | None]:
    training_run = model_version.training_run
    if training_run.dataset_version_id is None:
        return [], (
            f"production model type {training_run.model_type} was not trained against a DatasetVersion"
        )

    base_pool = _biomarker_base_pool(db, training_run.dataset_version_id)
    since = _now() - timedelta(days=RECENT_WINDOW_MAX_DAYS)
    recent_pool = segmentation_repository.list_recent_measurements_by_name(
        db, since=since, limit=RECENT_WINDOW_MAX_ROWS
    )

    names = sorted(set(base_pool) | set(recent_pool))
    results = [
        _ks_result(name, base_pool.get(name, []), recent_pool.get(name, []))
        for name in names
    ]
    return results, None


def _prediction_base_window(
    db: Session, *, model_version: ModelVersion
) -> tuple[list[str], str | None]:
    promotion_event = audit_repository.get_latest_event(
        db, action="model_version_promoted", resource_type="model_version",
        resource_id=str(model_version.id),
    )
    if promotion_event is None:
        return [], "no promotion audit event found"

    label = f"{model_version.name}@{model_version.id}"
    window_end = promotion_event.occurred_at + timedelta(days=BASE_PREDICTION_WINDOW_MAX_DAYS)
    stmt = (
        select(AIAnalysis.predicted_class)
        .where(
            AIAnalysis.status == AnalysisStatus.COMPLETED.value,
            AIAnalysis.model_version == label,
            AIAnalysis.completed_at >= promotion_event.occurred_at,
            AIAnalysis.completed_at <= window_end,
        )
        .order_by(AIAnalysis.completed_at.asc())
        .limit(BASE_PREDICTION_WINDOW_MAX_ROWS)
    )
    classes = [c for c in db.execute(stmt).scalars() if c is not None]
    return classes, None


def _prediction_recent_window(db: Session, *, model_version: ModelVersion) -> list[str]:
    label = f"{model_version.name}@{model_version.id}"
    since = _now() - timedelta(days=RECENT_WINDOW_MAX_DAYS)
    stmt = (
        select(AIAnalysis.predicted_class)
        .where(
            AIAnalysis.status == AnalysisStatus.COMPLETED.value,
            AIAnalysis.model_version == label,
            AIAnalysis.completed_at >= since,
        )
        .order_by(AIAnalysis.completed_at.desc())
        .limit(RECENT_WINDOW_MAX_ROWS)
    )
    return [c for c in db.execute(stmt).scalars() if c is not None]


def _psi(base_classes: list[str], recent_classes: list[str]) -> float:
    base_n, recent_n = len(base_classes), len(recent_classes)
    psi = 0.0
    for label in ALL_DIAGNOSIS_LABELS:
        p_base = base_classes.count(label) / base_n
        p_recent = recent_classes.count(label) / recent_n
        p_base = p_base if p_base > 0 else _PSI_EPSILON
        p_recent = p_recent if p_recent > 0 else _PSI_EPSILON
        psi += (p_recent - p_base) * math.log(p_recent / p_base)
    return psi


def _severity(psi: float) -> str:
    if psi > PSI_SIGNIFICANT_THRESHOLD:
        return "SIGNIFICANT"
    if psi >= PSI_MODERATE_THRESHOLD:
        return "MODERATE"
    return "NONE"


def _prediction_report(db: Session, *, model_version: ModelVersion) -> PredictionDriftResult:
    base_classes, skipped_reason = _prediction_base_window(db, model_version=model_version)
    recent_classes = _prediction_recent_window(db, model_version=model_version)
    base_n, recent_n = len(base_classes), len(recent_classes)

    if skipped_reason is None and (base_n < MIN_SAMPLE_SIZE or recent_n < MIN_SAMPLE_SIZE):
        skipped_reason = (
            f"insufficient samples for a PSI comparison (base={base_n}, recent={recent_n}, "
            f"minimum required={MIN_SAMPLE_SIZE} each)"
        )

    if skipped_reason is not None:
        return PredictionDriftResult(
            psi=None, base_sample_size=base_n, recent_sample_size=recent_n,
            severity="NONE", drift_detected=False, skipped_reason=skipped_reason,
        )

    psi = _psi(base_classes, recent_classes)
    severity = _severity(psi)
    return PredictionDriftResult(
        psi=psi, base_sample_size=base_n, recent_sample_size=recent_n,
        severity=severity, drift_detected=severity != "NONE", skipped_reason=None,
    )


def _update_metrics(report: ModelDriftReport) -> None:
    model_version_id = str(report.model_version_id)
    for biomarker in report.biomarkers:
        if biomarker.skipped_reason is not None:
            continue
        BIOMARKER_DRIFT_KS_STATISTIC.labels(
            model_version_id=model_version_id, biomarker_name=biomarker.biomarker_name
        ).set(biomarker.ks_statistic)
        BIOMARKER_DRIFT_PVALUE.labels(
            model_version_id=model_version_id, biomarker_name=biomarker.biomarker_name
        ).set(biomarker.p_value)
    if report.prediction.skipped_reason is None:
        PREDICTION_DRIFT_PSI.labels(model_version_id=model_version_id).set(report.prediction.psi)


def get_drift_report(db: Session, *, model_version: ModelVersion) -> ModelDriftReport:
    """Single entry point (EPIC-7 "Contrato técnico" point 3). Raises
    `ModelNotInProductionError` if `model_version.status != PRODUCTION` —
    deriva only has a well-defined meaning against the PRODUCTION model
    currently serving. Checks the in-memory cache before recalculating;
    recalculating also updates the Prometheus gauges as a side effect, here
    and only here — never on a `/metrics` scrape."""
    if model_version.status != ModelVersionStatus.PRODUCTION.value:
        raise ModelNotInProductionError("drift can only be evaluated for a PRODUCTION model version")

    cached = _cache.get(model_version.id)
    if cached is not None:
        computed_at, cached_report = cached
        if (_now() - computed_at).total_seconds() < _CACHE_TTL_SECONDS:
            return cached_report

    biomarkers, biomarkers_skipped_reason = _biomarker_report(db, model_version=model_version)
    prediction = _prediction_report(db, model_version=model_version)
    report = ModelDriftReport(
        model_version_id=model_version.id, evaluated_at=_now(),
        biomarkers=biomarkers, biomarkers_skipped_reason=biomarkers_skipped_reason,
        prediction=prediction,
    )
    _update_metrics(report)
    _cache[model_version.id] = (_now(), report)
    return report
