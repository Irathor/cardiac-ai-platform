import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.roles import RoleName
from app.db.session import get_db
from app.models.imaging_study import ImagingStudy
from app.models.user import User
from app.repositories import analysis_repository
from app.schemas.analysis import AIAnalysisOut, LlmExplanationOut
from app.services import analysis_service, llm_explanation_service, study_service
from app.services.llm_explanation_service import LlmExplanationError
from app.tasks.analysis_tasks import run_analysis

router = APIRouter()

_STUDY_NOT_FOUND = "Study not found"
_ANALYSIS_NOT_FOUND = "AI analysis not found"
_GRADCAM_NOT_AVAILABLE = "Grad-CAM attribution map not available for this analysis"
_NPY_CONTENT_TYPE = "application/octet-stream"


def _load_study_for_viewer(db: Session, study_id: uuid.UUID, viewer: User) -> ImagingStudy:
    try:
        return study_service.get_study_for_viewer(db, study_id, viewer)
    except study_service.StudyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_STUDY_NOT_FOUND) from exc


@router.post("/studies/{study_id}/analyses", status_code=status.HTTP_202_ACCEPTED)
def request_analysis(
    study_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> AIAnalysisOut:
    study = _load_study_for_viewer(db, study_id, current_user)
    analysis = analysis_service.create_analysis(db, actor=current_user, study=study)
    db.commit()
    db.refresh(analysis)
    run_analysis.delay(str(analysis.id))
    return AIAnalysisOut.model_validate(analysis)


@router.get("/studies/{study_id}/analyses")
def list_analyses(
    study_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> list[AIAnalysisOut]:
    _load_study_for_viewer(db, study_id, current_user)
    analyses = analysis_repository.list_for_study(db, study_id)
    return [AIAnalysisOut.model_validate(a) for a in analyses]


def _load_analysis(db: Session, analysis_id: uuid.UUID, viewer: User):
    analysis = analysis_repository.get_by_id(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ANALYSIS_NOT_FOUND)
    # An analysis is only reachable through a study the viewer is allowed to see —
    # same rule for reading the analysis itself and for reading its Grad-CAM map.
    _load_study_for_viewer(db, analysis.imaging_study_id, viewer)
    return analysis


@router.get("/analyses/{analysis_id}")
def get_analysis(
    analysis_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> AIAnalysisOut:
    analysis = _load_analysis(db, analysis_id, current_user)
    return AIAnalysisOut.model_validate(analysis)


@router.get("/analyses/{analysis_id}/gradcam")
def get_analysis_gradcam(
    analysis_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> Response:
    analysis = _load_analysis(db, analysis_id, current_user)
    if analysis.gradcam_storage_key is None:
        detail = analysis.gradcam_error or _GRADCAM_NOT_AVAILABLE
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    data = analysis_service.get_gradcam_file_bytes(analysis)
    return Response(content=data, media_type=_NPY_CONTENT_TYPE)


@router.post("/analyses/{analysis_id}/explanation")
def generate_analysis_explanation(
    analysis_id: uuid.UUID,
    force: bool = False,
    language: str = llm_explanation_service.DEFAULT_LANGUAGE,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> LlmExplanationOut:
    """EPIC-18 (+ follow-up: the explanation now follows the UI's own
    language toggle): returns the cached explanation if one exists in the
    requested language (unless `force=true`), otherwise generates one for
    real via the local Ollama model and caches it alongside the language it
    was written in — switching the UI language invalidates the cache for
    this analysis the same way `force=true` does, so the clinician never
    sees a stale-language suggestion silently reused. Always 200 — a
    generation failure (Ollama down, etc.) is an honest `error` field, not
    an HTTP error, same pattern as `gradcam_error`/`biomarker_consistency_error`
    elsewhere on this model."""
    analysis = _load_analysis(db, analysis_id, current_user)
    normalized_language = language if language in llm_explanation_service.SUPPORTED_LANGUAGES else llm_explanation_service.DEFAULT_LANGUAGE
    already_cached_in_language = (
        analysis.llm_explanation is not None and analysis.llm_explanation_language == normalized_language
    )
    if already_cached_in_language and not force:
        return LlmExplanationOut(explanation=analysis.llm_explanation, error=None)

    try:
        explanation = llm_explanation_service.generate_explanation(analysis, normalized_language)
    except LlmExplanationError as exc:
        analysis.llm_explanation_error = str(exc)
        db.commit()
        return LlmExplanationOut(explanation=None, error=str(exc))

    analysis.llm_explanation = explanation
    analysis.llm_explanation_language = normalized_language
    analysis.llm_explanation_error = None
    db.commit()
    return LlmExplanationOut(explanation=explanation, error=None)
