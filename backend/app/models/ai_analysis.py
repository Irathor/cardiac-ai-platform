import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AnalysisStatus
from app.db.base import Base
from app.db.types import GUID
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.imaging_study import ImagingStudy


class AIAnalysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One asynchronous disease-classification run for an ImagingStudy.

    Stores full per-class probabilities (not just the top class) and a
    feature attribution map, so a low-confidence or surprising result can
    always be inspected rather than trusted blindly — see
    docs/clinical-limitations.md. `model_version` is a demo-mode heuristic
    identifier until Phase 7 registers a real MLflow model version.
    """

    __tablename__ = "ai_analyses"

    imaging_study_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("imaging_studies.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default=AnalysisStatus.QUEUED.value, index=True)
    model_version: Mapped[str] = mapped_column(String(200))

    features: Mapped[dict | None] = mapped_column(JSON())
    predicted_class: Mapped[str | None] = mapped_column(String(100))
    probabilities: Mapped[dict | None] = mapped_column(JSON())
    # Denormalized from probabilities[predicted_class] at completion time —
    # kept as its own column (rather than computed on read) so the patient
    # list's low-confidence filter (see patient_repository.list_patients) can
    # do a plain, portable `WHERE confidence < x` instead of a per-dialect
    # JSON key lookup keyed by a dynamic (predicted_class) key.
    confidence: Mapped[float | None] = mapped_column(Float())
    feature_attributions: Mapped[dict | None] = mapped_column(JSON())
    error_message: Mapped[str | None] = mapped_column(String(2000))

    # EPIC-3: Grad-CAM attribution map for a real CNN3D_CLASSIFICATION run.
    # Only `storage_key` is persisted here (the (X,Y,Z) float32 array itself
    # lives in MinIO as a .npy — see app.services.analysis_service and
    # app.services.imaging_service.segmentation_storage_key for the exact
    # same pattern already used for Segmentation.storage_key). `gradcam_error`
    # holds an honest reason when Grad-CAM itself failed but the
    # classification succeeded (see CNN3D_NO_FEATURE_ATTRIBUTION_REASON's
    # sibling reasoning in app.services.analysis_service) — the analysis
    # still completes either way, this is never a reason to fail it.
    gradcam_storage_key: Mapped[str | None] = mapped_column(String(500))
    gradcam_error: Mapped[str | None] = mapped_column(String(2000))

    # EPIC-12: indirect consistency signal for a CNN3D_CLASSIFICATION run —
    # NOT an exact attribution (see feature_attributions above, which stays
    # null for CNN3D). Compares biomarkers derived by an independent U-Net
    # auto-segmentation of the same ED/ES series against the nearest-
    # centroid classifier's prototypes for the class CNN3D predicted (see
    # cardiac_ai_ml.classification.biomarker_consistency's `.as_dict()` for
    # the exact shape). `biomarker_consistency_error` holds an honest reason
    # when this signal itself failed (no U-Net PRODUCTION, runner down,
    # missing requesting user...) — same non-blocking pattern as
    # `gradcam_error` above, this never fails the AIAnalysis itself. Only
    # ever populated for the CNN3D_CLASSIFICATION path, never for the
    # tabular nearest-centroid path (which already has the real, exact
    # `feature_attributions` for that purpose).
    biomarker_consistency: Mapped[dict | None] = mapped_column(JSON())
    biomarker_consistency_error: Mapped[str | None] = mapped_column(String(2000))

    # EPIC-18: cached natural-language suggestion from a local LLM (Ollama +
    # Qwen2.5, see app.services.llm_explanation_service and ADR-9), built
    # only from the structured fields above (predicted_class/probabilities/
    # biomarker_consistency) — never from gradcam's raw array, which isn't
    # spatially meaningful (see gradcam_storage_key's own docstring above).
    # Cached because it's a real model call, not a cheap lookup; regenerated
    # only when the caller explicitly asks for that (see the API layer).
    # `llm_explanation_error` is the same honest-failure pattern as
    # gradcam_error/biomarker_consistency_error — generation failing (e.g.
    # Ollama not running) never fails the AIAnalysis itself.
    llm_explanation: Mapped[str | None] = mapped_column(Text())
    llm_explanation_error: Mapped[str | None] = mapped_column(String(2000))
    # Which language `llm_explanation` was written in ("en"/"es") — lets the
    # API tell a stale-language cached explanation apart from a fresh one
    # when the UI's language toggle changes (see
    # app.services.llm_explanation_service.SUPPORTED_LANGUAGES).
    llm_explanation_language: Mapped[str | None] = mapped_column(String(10))

    requested_by: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    imaging_study: Mapped["ImagingStudy"] = relationship()

    @property
    def gradcam_available(self) -> bool:
        return self.gradcam_storage_key is not None

    @property
    def llm_explanation_available(self) -> bool:
        return self.llm_explanation is not None
