"""Real auto-segmentation: when a U-Net model is PRODUCTION (see
app.core.model_registry.MODEL_NAME_UNET), run it over an already-uploaded
ImageSeries and create a real `Segmentation` from its predicted mask —
the same domain entity a manually-uploaded/corrected mask already uses
(see app.services.imaging_service.upload_segmentation), not `AIAnalysis`
(see docs/epics/EPIC-2-servir-modelos-reales-inferencia.md's refinement
note on why: U-Net is a segmentation model, not a diagnosis classifier).

Deliberately does NOT call `imaging_service.upload_segmentation` directly:
that function validates the uploaded mask's shape against the series'
*native* shape (correct for a human re-uploading a corrected mask at the
same resolution they downloaded). The U-Net predicts at its own fixed
working resolution (`cardiac_ai_ml.dl.preprocessing.DEFAULT_TARGET_SPACING_XY`/
`DEFAULT_SLICE_SIZE`, see `predict_volume`'s docstring) — a real, deliberate
resolution mismatch, not a bug — so that check would always fail here. What
*is* reused verbatim is the actual biomarker computation
(`compute_frame_biomarkers`, the exact same call `upload_segmentation`
makes) and the same storage-key convention, so an auto-generated
segmentation is indistinguishable from a manual one everywhere downstream
(viewer, biomarker list, AIAnalysis feature collection) except for its
`model_version` field.
"""
import tempfile
from pathlib import Path

import nibabel as nib
import numpy as np
from cardiac_ai_ml.biomarkers import VoxelSpacing, compute_frame_biomarkers
from sqlalchemy.orm import Session

from app.core.model_registry import MODEL_NAME_UNET
from app.models.image_series import ImageSeries
from app.models.segmentation import Segmentation
from app.models.user import User
from app.repositories import audit_repository, model_repository, segmentation_repository
from app.services import dl_inference_client, imaging_service
from app.storage import object_storage


class ModelNotAvailableError(ValueError):
    """Raised when no ModelVersion named MODEL_NAME_UNET is currently
    PRODUCTION — auto-segmentation has nothing to run."""


def _mask_to_nifti_bytes(mask: np.ndarray, spacing: VoxelSpacing) -> bytes:
    affine = np.diag([spacing.x_mm, spacing.y_mm, spacing.z_mm, 1.0]).astype(np.float64)
    image = nib.Nifti1Image(mask.astype(np.int16), affine)
    with tempfile.NamedTemporaryFile(suffix=".nii.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        nib.save(image, tmp_path)
        return tmp_path.read_bytes()
    finally:
        tmp_path.unlink(missing_ok=True)


def generate_auto_segmentation(db: Session, *, actor: User, series: ImageSeries) -> Segmentation:
    production = model_repository.get_production(db, MODEL_NAME_UNET)
    if production is None:
        raise ModelNotAvailableError(f"no PRODUCTION model named {MODEL_NAME_UNET!r} is currently active")

    file_bytes = imaging_service.get_series_file_bytes(series)
    mask, spacing_x, spacing_y, spacing_z = dl_inference_client.segment_unet(image_bytes=file_bytes)
    spacing = VoxelSpacing(x_mm=spacing_x, y_mm=spacing_y, z_mm=spacing_z)

    model_version_label = f"{production.name}@{production.id}"
    segmentation = segmentation_repository.create(
        db,
        image_series_id=series.id,
        created_by=actor.id,
        storage_key="",
        model_version=model_version_label,
    )
    segmentation.storage_key = imaging_service.segmentation_storage_key(series.id, segmentation.id)
    db.flush()

    object_storage.get_storage().put_bytes(
        segmentation.storage_key,
        _mask_to_nifti_bytes(mask, spacing),
        content_type="application/octet-stream",
    )

    biomarkers = compute_frame_biomarkers(mask.astype(np.int32), spacing)
    segmentation_repository.add_measurements(
        db, segmentation_id=segmentation.id, measurements=biomarkers.as_measurements()
    )

    audit_repository.record(
        db, user_id=actor.id, action="auto_segmentation_generated", resource_type="segmentation",
        resource_id=str(segmentation.id), result="success",
        event_metadata={"image_series_id": str(series.id), "model_version": model_version_label},
    )
    return segmentation
