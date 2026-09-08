"""Disease-classification orchestration.

`create_analysis` (called from the request/response path) only ever writes a
QUEUED row and hands off to Celery — it never imports the ml/ package itself.
`execute_analysis` (called only from app.tasks.analysis_tasks, i.e. from the
Celery worker) does the actual feature collection and classification.
"""
import uuid
from datetime import datetime, timezone

from cardiac_ai_ml.biomarkers import ejection_fraction_percent
from cardiac_ai_ml.classification import (
    DiagnosisClass,
    classify_demo,
    classify_with_prototypes,
    explain_demo,
    explain_with_prototypes,
)
from sqlalchemy.orm import Session

from app.core.enums import AnalysisStatus
from app.core.model_registry import MODEL_NAME
from app.models.ai_analysis import AIAnalysis
from app.models.image_series import ImageSeries
from app.models.imaging_study import ImagingStudy
from app.models.user import User
from app.repositories import (
    analysis_repository,
    audit_repository,
    image_series_repository,
    model_repository,
    segmentation_repository,
)

PENDING_MODEL_VERSION = "pending"
DEMO_MODEL_VERSION = "demo-heuristic-v1"


class MissingPhaseDataError(ValueError):
    """Raised when a study doesn't have a segmented ED and ES series yet."""


def create_analysis(db: Session, *, actor: User, study: ImagingStudy) -> AIAnalysis:
    analysis = analysis_repository.create(
        db,
        imaging_study_id=study.id,
        requested_by=actor.id,
        status=AnalysisStatus.QUEUED.value,
        # Overwritten in execute_analysis with whichever model actually ran
        # (production, if one exists at that time, else the demo heuristic) —
        # this is just a placeholder for the QUEUED window.
        model_version=PENDING_MODEL_VERSION,
    )
    audit_repository.record(
        db, user_id=actor.id, action="ai_analysis_requested", resource_type="ai_analysis",
        resource_id=str(analysis.id), result="success",
        event_metadata={"imaging_study_id": str(study.id)},
    )
    return analysis


def _latest_segmentation_biomarkers(db: Session, series: ImageSeries) -> dict[str, float] | None:
    segmentations = segmentation_repository.list_for_series(db, series.id)
    if not segmentations:
        return None
    latest = segmentations[-1]
    measurements = segmentation_repository.list_measurements(db, latest.id)
    return {m.name: m.value for m in measurements}


def collect_features(db: Session, study: ImagingStudy) -> dict[str, float]:
    series_list = image_series_repository.list_for_study(db, study.id)
    ed_series = next((s for s in series_list if s.phase == "ED"), None)
    es_series = next((s for s in series_list if s.phase == "ES"), None)
    if ed_series is None or es_series is None:
        raise MissingPhaseDataError(
            "study needs an ED and an ES image series (ImageSeries.phase) to compute an ejection fraction"
        )

    ed_biomarkers = _latest_segmentation_biomarkers(db, ed_series)
    es_biomarkers = _latest_segmentation_biomarkers(db, es_series)
    if ed_biomarkers is None or es_biomarkers is None:
        raise MissingPhaseDataError("both the ED and ES series need at least one segmentation")

    edv = ed_biomarkers["LV_VOLUME"]
    esv = es_biomarkers["LV_VOLUME"]
    return {
        "EJECTION_FRACTION": ejection_fraction_percent(edv, esv),
        "LV_EDV": edv,
        "RV_EDV": ed_biomarkers["RV_VOLUME"],
        "LV_MASS": ed_biomarkers["MYOCARDIAL_MASS"],
    }


def execute_analysis(db: Session, *, analysis_id: uuid.UUID) -> None:
    """Runs entirely inside the Celery worker (see app.tasks.analysis_tasks) —
    never call this from an HTTP request handler."""
    analysis = analysis_repository.get_by_id(db, analysis_id)
    if analysis is None:
        return

    analysis.status = AnalysisStatus.RUNNING.value
    db.flush()

    study = db.get(ImagingStudy, analysis.imaging_study_id)
    try:
        if study is None:
            raise MissingPhaseDataError("imaging study no longer exists")
        features = collect_features(db, study)

        production_model = model_repository.get_production(db, MODEL_NAME)
        if production_model is not None:
            prototypes = production_model.prototypes
            baseline = prototypes[DiagnosisClass.NORMAL.value]
            result = classify_with_prototypes(features, prototypes)
            attributions = explain_with_prototypes(features, prototypes, baseline)
            analysis.model_version = f"{production_model.name}@{production_model.id}"
        else:
            result = classify_demo(features)
            attributions = explain_demo(features)
            analysis.model_version = DEMO_MODEL_VERSION

        analysis.features = features
        analysis.predicted_class = result.predicted_class
        analysis.probabilities = result.probabilities
        analysis.confidence = result.confidence
        analysis.feature_attributions = attributions
        analysis.status = AnalysisStatus.COMPLETED.value
        analysis.completed_at = datetime.now(timezone.utc)
        audit_repository.record(
            db, user_id=analysis.requested_by, action="ai_analysis_completed",
            resource_type="ai_analysis", resource_id=str(analysis.id), result="success",
            event_metadata={"predicted_class": analysis.predicted_class},
        )
    except MissingPhaseDataError as exc:
        analysis.status = AnalysisStatus.FAILED.value
        analysis.error_message = str(exc)
        audit_repository.record(
            db, user_id=analysis.requested_by, action="ai_analysis_failed",
            resource_type="ai_analysis", resource_id=str(analysis.id), result="failure",
            event_metadata={"error": str(exc)},
        )
    db.flush()
