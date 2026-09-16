"""Disease-classification orchestration.

`create_analysis` (called from the request/response path) only ever writes a
QUEUED row and hands off to Celery — it never imports the ml/ package itself.
`execute_analysis` (called only from app.tasks.analysis_tasks, i.e. from the
Celery worker) does the actual feature collection and classification.
"""
import io
import uuid
from datetime import datetime, timezone

import numpy as np
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
from app.core.model_registry import MODEL_NAME, MODEL_NAME_CNN3D
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
from app.services import dl_inference_client, imaging_service
from app.services.dl_inference_client import InferenceRunnerError
from app.storage import object_storage

PENDING_MODEL_VERSION = "pending"
DEMO_MODEL_VERSION = "demo-heuristic-v1"

# Why feature_values/feature_attributions are left null for a CNN3D analysis
# (see execute_analysis): both only make sense for the tabular nearest-centroid
# path — a plain biomarker vector the model actually scored, and exact Shapley
# attributions over that same vector (see cardiac_ai_ml.classification's module
# docstring). The CNN3D classifies directly from raw image volumes, no
# biomarker vector is ever computed or scored, so there is nothing honest to
# attribute per-feature; fabricating a fake vector just to fill the column
# would misrepresent what the model actually used. Real per-voxel
# explainability for the CNN3D (Grad-CAM) is EPIC-3, not this Epic.
CNN3D_NO_FEATURE_ATTRIBUTION_REASON = (
    "CNN3D_CLASSIFICATION predicts directly from raw ED/ES image volumes, not from a "
    "tabular biomarker vector — there is no feature vector to attribute. See "
    "EPIC-3 for real Grad-CAM-based image explainability of this model."
)

# EPIC-3: why a failed Grad-CAM never fails the whole AIAnalysis — the
# classification itself is a separate, already-successful forward pass; see
# docs/epics/EPIC-3-gradcam-integrado-flujo-servido.md point 4. Analogous to
# CNN3D_NO_FEATURE_ATTRIBUTION_REASON above, but here the reason genuinely
# varies case to case (layer hook, zero gradient...) so it's worth surfacing
# per-analysis instead of a single static string.
_GRADCAM_UNKNOWN_REASON = "no reason reported by the inference runner"


def _gradcam_storage_key(analysis_id: uuid.UUID) -> str:
    return f"analyses/{analysis_id}/gradcam.npy"


class MissingPhaseDataError(ValueError):
    """Raised when a study doesn't have an ED and an ES image series (and,
    for the nearest-centroid path, a segmentation on each) yet."""


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


def _ed_es_series(db: Session, study: ImagingStudy) -> tuple[ImageSeries, ImageSeries]:
    """Shared by `collect_features` (tabular nearest-centroid path, which
    also needs each series' segmentation) and the CNN3D path (which needs
    only the raw ED/ES series themselves, no segmentation at all)."""
    series_list = image_series_repository.list_for_study(db, study.id)
    ed_series = next((s for s in series_list if s.phase == "ED"), None)
    es_series = next((s for s in series_list if s.phase == "ES"), None)
    if ed_series is None or es_series is None:
        raise MissingPhaseDataError(
            "study needs an ED and an ES image series (ImageSeries.phase) to compute an ejection fraction"
        )
    return ed_series, es_series


def collect_features(db: Session, study: ImagingStudy) -> dict[str, float]:
    ed_series, es_series = _ed_es_series(db, study)

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

        # CNN3D_CLASSIFICATION takes priority over the nearest-centroid
        # classifier when both happen to be marked PRODUCTION at once (an
        # unusual admin state — the two live under different ModelVersion
        # `name`s, see app.core.model_registry, so nothing stops both being
        # PRODUCTION simultaneously): it's the genuinely-trained deep model,
        # a strictly more capable classifier than the heuristic/nearest-
        # centroid path, so it's the more meaningful one to serve live.
        production_cnn3d = model_repository.get_production(db, MODEL_NAME_CNN3D)
        if production_cnn3d is not None:
            ed_series, es_series = _ed_es_series(db, study)
            ed_bytes = imaging_service.get_series_file_bytes(ed_series)
            es_bytes = imaging_service.get_series_file_bytes(es_series)
            prediction = dl_inference_client.classify_cnn3d(ed_bytes=ed_bytes, es_bytes=es_bytes)

            # See CNN3D_NO_FEATURE_ATTRIBUTION_REASON above: no tabular
            # biomarker vector exists for this model, so features/
            # feature_attributions stay honestly null rather than fabricated.
            analysis.features = None
            analysis.predicted_class = prediction["predicted_class"]
            analysis.probabilities = prediction["probabilities"]
            analysis.confidence = prediction["probabilities"][prediction["predicted_class"]]
            analysis.feature_attributions = None
            analysis.model_version = f"{production_cnn3d.name}@{production_cnn3d.id}"

            gradcam_attribution = prediction.get("gradcam_attribution")
            if gradcam_attribution is not None:
                buffer = io.BytesIO()
                np.save(buffer, np.ascontiguousarray(gradcam_attribution, dtype=np.float32))
                storage_key = _gradcam_storage_key(analysis.id)
                object_storage.get_storage().put_bytes(
                    storage_key, buffer.getvalue(), content_type="application/octet-stream"
                )
                analysis.gradcam_storage_key = storage_key
                analysis.gradcam_error = None
            else:
                analysis.gradcam_storage_key = None
                reason = prediction.get("gradcam_error") or _GRADCAM_UNKNOWN_REASON
                analysis.gradcam_error = f"Grad-CAM no disponible para este análisis: {reason}"
        else:
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
    except (MissingPhaseDataError, InferenceRunnerError) as exc:
        analysis.status = AnalysisStatus.FAILED.value
        analysis.error_message = str(exc)
        audit_repository.record(
            db, user_id=analysis.requested_by, action="ai_analysis_failed",
            resource_type="ai_analysis", resource_id=str(analysis.id), result="failure",
            event_metadata={"error": str(exc)},
        )
    db.flush()


def get_gradcam_file_bytes(analysis: AIAnalysis) -> bytes:
    """Raises if `analysis.gradcam_storage_key` is None — callers (the
    `/analyses/{id}/gradcam` endpoint) must check `gradcam_storage_key`
    first and respond honestly (404 with `gradcam_error` if present) rather
    than call this at all when there's no map to serve."""
    return object_storage.get_storage().get_bytes(analysis.gradcam_storage_key)
