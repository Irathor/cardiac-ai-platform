import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.roles import RoleName
from app.db.session import get_db
from app.models.imaging_study import ImagingStudy
from app.models.user import User
from app.repositories import analysis_repository
from app.schemas.analysis import AIAnalysisOut
from app.services import analysis_service, study_service
from app.tasks.analysis_tasks import run_analysis

router = APIRouter()

_STUDY_NOT_FOUND = "Study not found"
_ANALYSIS_NOT_FOUND = "AI analysis not found"


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


@router.get("/analyses/{analysis_id}")
def get_analysis(
    analysis_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> AIAnalysisOut:
    analysis = analysis_repository.get_by_id(db, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_ANALYSIS_NOT_FOUND)
    # An analysis is only reachable through a study the viewer is allowed to see.
    _load_study_for_viewer(db, analysis.imaging_study_id, current_user)
    return AIAnalysisOut.model_validate(analysis)
