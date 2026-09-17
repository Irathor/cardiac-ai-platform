"""Read-only showcase of LIME vs. Shapley + Grad-CAM artifacts already
generated offline by ml/scripts/run_explainability_showcase.py (EPIC-1),
see docs/epics/EPIC-15-showcase-lime-vs-shapley.md "Contrato técnico".
Nothing here recalculates LIME, Shapley, or Grad-CAM — this router only
serves the JSON/PNGs already on disk under data/models/explainability/.

Same RBAC as app/api/v1/models.py's _VIEW_ROLES: this is an
engineering/model-governance artifact, not a clinical tool, so DOCTOR is
deliberately excluded."""
from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.core.config import get_settings
from app.core.deps import require_roles
from app.core.roles import RoleName
from app.models.user import User
from app.schemas.explainability import ExplainabilityShowcaseOut
from app.services import explainability_service

router = APIRouter()

_VIEW_ROLES = (RoleName.ML_ENGINEER, RoleName.MODEL_APPROVER, RoleName.ADMIN)


@router.get("/explainability/showcase")
def get_explainability_showcase(
    current_user: User = Depends(require_roles(*_VIEW_ROLES)),
) -> ExplainabilityShowcaseOut:
    settings = get_settings()
    try:
        showcase = explainability_service.load_showcase(settings.data_root)
    except explainability_service.ShowcaseNotGeneratedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ExplainabilityShowcaseOut.model_validate(showcase)


@router.get("/explainability/showcase/images/{filename}")
def get_explainability_showcase_image(
    filename: str,
    current_user: User = Depends(require_roles(*_VIEW_ROLES)),
) -> Response:
    settings = get_settings()
    try:
        image_bytes = explainability_service.load_showcase_image_bytes(settings.data_root, filename)
    except explainability_service.ShowcaseNotGeneratedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except explainability_service.ImageNotAllowedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found") from exc
    return Response(content=image_bytes, media_type="image/png")
