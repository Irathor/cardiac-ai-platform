import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.core.roles import RoleName
from app.core.uploads import UploadTooLargeError, read_upload_within_limit
from app.db.session import get_db
from app.models.image_series import ImageSeries
from app.models.imaging_study import ImagingStudy
from app.models.user import User
from app.repositories import image_series_repository, segmentation_repository
from app.schemas.imaging import BiomarkerMeasurementOut, ImageSeriesOut, SegmentationOut
from app.services import imaging_service, study_service

router = APIRouter()

_STUDY_NOT_FOUND = "Study not found"
_SERIES_NOT_FOUND = "Image series not found"
_SEGMENTATION_NOT_FOUND = "Segmentation not found"
_NIFTI_CONTENT_TYPE = "application/octet-stream"


def _load_study_for_viewer(db: Session, study_id: uuid.UUID, viewer: User) -> ImagingStudy:
    try:
        return study_service.get_study_for_viewer(db, study_id, viewer)
    except study_service.StudyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_STUDY_NOT_FOUND) from exc


def _load_series(db: Session, series_id: uuid.UUID, viewer: User) -> ImageSeries:
    series = image_series_repository.get_by_id(db, series_id)
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SERIES_NOT_FOUND)
    # A series is only reachable through a study the viewer is allowed to see.
    _load_study_for_viewer(db, series.imaging_study_id, viewer)
    return series


@router.post("/studies/{study_id}/series", status_code=status.HTTP_201_CREATED)
async def upload_series(
    study_id: uuid.UUID,
    file: UploadFile = File(...),
    series_type: str = Form("CINE_SHORT_AXIS"),
    phase: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> ImageSeriesOut:
    study = _load_study_for_viewer(db, study_id, current_user)
    try:
        file_bytes = await read_upload_within_limit(file)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    try:
        series = imaging_service.upload_series(
            db, actor=current_user, study=study, file_bytes=file_bytes,
            series_type=series_type, phase=phase,
        )
    except imaging_service.InvalidNiftiFileError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    db.commit()
    db.refresh(series)
    return ImageSeriesOut.model_validate(series)


@router.get("/studies/{study_id}/series")
def list_series(
    study_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> list[ImageSeriesOut]:
    _load_study_for_viewer(db, study_id, current_user)
    series = image_series_repository.list_for_study(db, study_id)
    return [ImageSeriesOut.model_validate(s) for s in series]


@router.get("/series/{series_id}/file")
def get_series_file(
    series_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> Response:
    series = _load_series(db, series_id, current_user)
    data = imaging_service.get_series_file_bytes(series)
    return Response(content=data, media_type=_NIFTI_CONTENT_TYPE)


@router.post("/series/{series_id}/segmentations", status_code=status.HTTP_201_CREATED)
async def upload_segmentation(
    series_id: uuid.UUID,
    file: UploadFile = File(...),
    model_version: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> SegmentationOut:
    series = _load_series(db, series_id, current_user)
    try:
        file_bytes = await read_upload_within_limit(file)
    except UploadTooLargeError as exc:
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)) from exc
    try:
        segmentation = imaging_service.upload_segmentation(
            db, actor=current_user, series=series, file_bytes=file_bytes, model_version=model_version,
        )
    except imaging_service.InvalidNiftiFileError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except imaging_service.SegmentationShapeMismatchError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    db.commit()
    db.refresh(segmentation)
    return SegmentationOut.model_validate(segmentation)


@router.get("/series/{series_id}/segmentations")
def list_segmentations(
    series_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> list[SegmentationOut]:
    _load_series(db, series_id, current_user)
    segmentations = segmentation_repository.list_for_series(db, series_id)
    return [SegmentationOut.model_validate(s) for s in segmentations]


def _load_segmentation(db: Session, segmentation_id: uuid.UUID, viewer: User):
    segmentation = segmentation_repository.get_by_id(db, segmentation_id)
    if segmentation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_SEGMENTATION_NOT_FOUND)
    _load_series(db, segmentation.image_series_id, viewer)
    return segmentation


@router.get("/segmentations/{segmentation_id}/file")
def get_segmentation_file(
    segmentation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> Response:
    segmentation = _load_segmentation(db, segmentation_id, current_user)
    data = imaging_service.get_segmentation_file_bytes(segmentation)
    return Response(content=data, media_type=_NIFTI_CONTENT_TYPE)


@router.get("/segmentations/{segmentation_id}/biomarkers")
def list_biomarkers(
    segmentation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(RoleName.ADMIN, RoleName.DOCTOR)),
) -> list[BiomarkerMeasurementOut]:
    _load_segmentation(db, segmentation_id, current_user)
    measurements = segmentation_repository.list_measurements(db, segmentation_id)
    return [BiomarkerMeasurementOut.model_validate(m) for m in measurements]
