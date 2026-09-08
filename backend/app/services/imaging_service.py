"""Imaging/segmentation/biomarker orchestration: decode the uploaded NIfTI,
store the raw bytes, and (for a segmentation) compute biomarkers synchronously.

Voxel-counting biomarkers are cheap (milliseconds, pure numpy) — unlike a real
model inference (Phase 5), this does not need to go through Celery; see the
"why these boundaries" note in docs/architecture.md.
"""
import tempfile
import uuid
from pathlib import Path

import nibabel as nib
import numpy as np
from cardiac_ai_ml.biomarkers import VoxelSpacing, compute_frame_biomarkers
from sqlalchemy.orm import Session

from app.models.image_series import ImageSeries
from app.models.imaging_study import ImagingStudy
from app.models.segmentation import Segmentation
from app.models.user import User
from app.repositories import audit_repository, image_series_repository, segmentation_repository
from app.storage import object_storage


class InvalidNiftiFileError(ValueError):
    pass


class SegmentationShapeMismatchError(ValueError):
    pass


def _decode_nifti(file_bytes: bytes) -> tuple[np.ndarray, tuple[float, float, float]]:
    """nibabel needs a real file path to memory-map a NIfTI file, so the
    uploaded bytes are written to a throwaway temp file first."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = Path(tmp.name)
        try:
            image = nib.load(tmp_path)
            data = np.asarray(image.dataobj)
            spacing = tuple(float(z) for z in image.header.get_zooms()[:3])
        finally:
            tmp_path.unlink(missing_ok=True)
    except Exception as exc:  # nibabel raises several distinct error types for bad files
        raise InvalidNiftiFileError(f"could not decode NIfTI file: {exc}") from exc

    if data.ndim != 3:
        raise InvalidNiftiFileError(f"expected a 3D NIfTI volume, got {data.ndim}D")
    if len(spacing) != 3:
        raise InvalidNiftiFileError("NIfTI header is missing voxel spacing")
    return data, spacing


def _series_storage_key(imaging_study_id: uuid.UUID, series_id: uuid.UUID) -> str:
    return f"studies/{imaging_study_id}/series/{series_id}.nii.gz"


def _segmentation_storage_key(image_series_id: uuid.UUID, segmentation_id: uuid.UUID) -> str:
    return f"series/{image_series_id}/segmentations/{segmentation_id}.nii.gz"


def upload_series(
    db: Session,
    *,
    actor: User,
    study: ImagingStudy,
    file_bytes: bytes,
    series_type: str,
    phase: str | None,
) -> ImageSeries:
    data, spacing = _decode_nifti(file_bytes)

    series = image_series_repository.create(
        db,
        imaging_study_id=study.id,
        uploaded_by=actor.id,
        series_type=series_type,
        phase=phase,
        storage_key="",  # filled in below once the series has an id
        voxel_spacing_x_mm=spacing[0],
        voxel_spacing_y_mm=spacing[1],
        voxel_spacing_z_mm=spacing[2],
        shape_x=data.shape[0],
        shape_y=data.shape[1],
        shape_z=data.shape[2],
    )
    series.storage_key = _series_storage_key(study.id, series.id)
    db.flush()

    object_storage.get_storage().put_bytes(
        series.storage_key, file_bytes, content_type="application/octet-stream"
    )

    audit_repository.record(
        db, user_id=actor.id, action="image_series_uploaded", resource_type="image_series",
        resource_id=str(series.id), result="success",
        event_metadata={"imaging_study_id": str(study.id), "series_type": series_type},
    )
    return series


def upload_segmentation(
    db: Session,
    *,
    actor: User,
    series: ImageSeries,
    file_bytes: bytes,
    model_version: str | None = None,
) -> Segmentation:
    mask, _mask_spacing = _decode_nifti(file_bytes)
    expected_shape = (series.shape_x, series.shape_y, series.shape_z)
    if mask.shape != expected_shape:
        raise SegmentationShapeMismatchError(
            f"segmentation shape {mask.shape} does not match series shape {expected_shape}"
        )

    segmentation = segmentation_repository.create(
        db,
        image_series_id=series.id,
        created_by=actor.id,
        storage_key="",
        model_version=model_version,
    )
    segmentation.storage_key = _segmentation_storage_key(series.id, segmentation.id)
    db.flush()

    object_storage.get_storage().put_bytes(
        segmentation.storage_key, file_bytes, content_type="application/octet-stream"
    )

    spacing = VoxelSpacing(
        x_mm=series.voxel_spacing_x_mm,
        y_mm=series.voxel_spacing_y_mm,
        z_mm=series.voxel_spacing_z_mm,
    )
    biomarkers = compute_frame_biomarkers(mask.astype(np.int32), spacing)
    segmentation_repository.add_measurements(
        db, segmentation_id=segmentation.id, measurements=biomarkers.as_measurements()
    )

    audit_repository.record(
        db, user_id=actor.id, action="segmentation_uploaded", resource_type="segmentation",
        resource_id=str(segmentation.id), result="success",
        event_metadata={"image_series_id": str(series.id), "model_version": model_version},
    )
    return segmentation


def get_series_file_bytes(series: ImageSeries) -> bytes:
    return object_storage.get_storage().get_bytes(series.storage_key)


def get_segmentation_file_bytes(segmentation: Segmentation) -> bytes:
    return object_storage.get_storage().get_bytes(segmentation.storage_key)
