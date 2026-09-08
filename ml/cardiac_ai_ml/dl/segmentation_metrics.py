"""Per-structure, per-phase segmentation validation metrics — Dice/IoU/HD95/
ASSD/volume-error/plausibility, computed from a single (prediction, target)
pair of 3D label masks plus real voxel spacing (so distance metrics come out
in millimetres, not voxels).

Distance-based metrics (HD95, ASSD) use `scipy.ndimage.distance_transform_edt`
with the mask's real spacing as `sampling` — a distance-transform pass is
O(n) in voxel count, versus the O(n*m) a naive point-to-point surface
distance loop would cost, which matters at ACDC's ~200x200x10 volume sizes.

Every distance/volume metric here is computed for one structure at a time
(binary mask) — callers loop over CardiacLabels.{left_ventricle_cavity,
right_ventricle_cavity,myocardium} x {ED,ES} and aggregate across patients.
"""
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import binary_dilation, binary_erosion, distance_transform_edt, label as connected_components_label

Spacing = tuple[float, float, float]


def binary_dice(prediction: np.ndarray, target: np.ndarray, eps: float = 1e-6) -> float:
    intersection = np.count_nonzero(prediction & target)
    denom = np.count_nonzero(prediction) + np.count_nonzero(target)
    if denom == 0:
        return 1.0  # neither present — vacuous but correct match, see dl/metrics.py
    return (2.0 * intersection + eps) / (denom + eps)


def binary_iou(prediction: np.ndarray, target: np.ndarray, eps: float = 1e-6) -> float:
    intersection = np.count_nonzero(prediction & target)
    union = np.count_nonzero(prediction | target)
    if union == 0:
        return 1.0
    return (intersection + eps) / (union + eps)


@dataclass(frozen=True)
class VoxelConfusion:
    precision: float
    recall: float
    specificity: float


def voxel_confusion(prediction: np.ndarray, target: np.ndarray) -> VoxelConfusion:
    tp = np.count_nonzero(prediction & target)
    fp = np.count_nonzero(prediction & ~target)
    fn = np.count_nonzero(~prediction & target)
    tn = np.count_nonzero(~prediction & ~target)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    specificity = tn / (tn + fp) if (tn + fp) else 1.0
    return VoxelConfusion(precision=precision, recall=recall, specificity=specificity)


def volume_ml(mask: np.ndarray, spacing: Spacing) -> float:
    voxel_volume = (spacing[0] * spacing[1] * spacing[2]) / 1000.0
    return float(np.count_nonzero(mask)) * voxel_volume


def volumetric_similarity(prediction: np.ndarray, target: np.ndarray, spacing: Spacing) -> float:
    """VS = 1 - |Vp - Vt| / (Vp + Vt) (Taha & Hanbury 2015) — 1.0 is a
    perfect volume match, independent of spatial overlap (a metric can score
    well here while scoring poorly on Dice, if the predicted blob is the
    right size but the wrong shape/location)."""
    vp, vt = volume_ml(prediction, spacing), volume_ml(target, spacing)
    if vp + vt == 0:
        return 1.0
    return 1.0 - abs(vp - vt) / (vp + vt)


def relative_volume_error_percent(prediction: np.ndarray, target: np.ndarray, spacing: Spacing) -> float | None:
    """Signed (Vp - Vt) / Vt * 100 — None (not zero) when the reference
    volume is empty, since the error is undefined rather than infinite/zero."""
    vt = volume_ml(target, spacing)
    if vt == 0:
        return None
    vp = volume_ml(prediction, spacing)
    return (vp - vt) / vt * 100.0


def is_empty_mask(mask: np.ndarray) -> bool:
    return not np.any(mask)


def connected_components_count(mask: np.ndarray) -> int:
    if not np.any(mask):
        return 0
    _, count = connected_components_label(mask)
    return int(count)


def _surface_voxels(mask: np.ndarray) -> np.ndarray:
    """Boundary voxels of a binary mask — foreground voxels with at least
    one background neighbor."""
    eroded = binary_erosion(mask, border_value=0)
    return mask & ~eroded


@dataclass(frozen=True)
class SurfaceDistanceResult:
    hausdorff_distance_mm: float | None
    hausdorff_distance_95_mm: float | None
    average_symmetric_surface_distance_mm: float | None


def surface_distances(prediction: np.ndarray, target: np.ndarray, spacing: Spacing) -> SurfaceDistanceResult:
    """None for every field when either mask is empty and the other isn't
    (an undefined distance, not a fabricated worst-case number) or when both
    are empty (a vacuous match with no boundary to measure, unlike Dice's
    convention this is reported as None rather than a fake "perfect" 0.0,
    since "no distance to measure" and "measured zero distance" are not the
    same claim)."""
    pred_empty, target_empty = not np.any(prediction), not np.any(target)
    if pred_empty or target_empty:
        return SurfaceDistanceResult(None, None, None)

    surface_pred = _surface_voxels(prediction)
    surface_target = _surface_voxels(target)

    dt_target = distance_transform_edt(~target, sampling=spacing)
    dt_pred = distance_transform_edt(~prediction, sampling=spacing)

    dist_pred_to_target = dt_target[surface_pred]
    dist_target_to_pred = dt_pred[surface_target]

    hd = float(max(dist_pred_to_target.max(), dist_target_to_pred.max()))
    hd95 = float(max(np.percentile(dist_pred_to_target, 95), np.percentile(dist_target_to_pred, 95)))
    assd = float(
        (dist_pred_to_target.sum() + dist_target_to_pred.sum())
        / (len(dist_pred_to_target) + len(dist_target_to_pred))
    )
    return SurfaceDistanceResult(hd, hd95, assd)


@dataclass(frozen=True)
class AnatomicalPlausibility:
    lv_multiple_components: bool
    rv_multiple_components: bool
    lv_not_enclosed_by_myocardium: bool

    @property
    def any_violation(self) -> bool:
        return self.lv_multiple_components or self.rv_multiple_components or self.lv_not_enclosed_by_myocardium


def check_anatomical_plausibility(
    lv_mask: np.ndarray, rv_mask: np.ndarray, myocardium_mask: np.ndarray, *, enclosure_threshold: float = 0.5
) -> AnatomicalPlausibility:
    """Simple geometric plausibility heuristic — NOT a clinical validator.
    Flags two things a correct segmentation should never do: (1) the LV or
    RV cavity split into multiple disconnected blobs (each ventricle is one
    contiguous cavity per volume); (2) the LV cavity mostly bordering
    background directly instead of myocardium (a real LV is wrapped in
    myocardial wall, not floating next to empty space)."""
    lv_components = connected_components_count(lv_mask)
    rv_components = connected_components_count(rv_mask)

    lv_not_enclosed = False
    if np.any(lv_mask):
        neighborhood = binary_dilation(lv_mask) & ~lv_mask
        neighborhood_count = np.count_nonzero(neighborhood)
        if neighborhood_count > 0:
            myocardium_overlap = np.count_nonzero(neighborhood & myocardium_mask)
            lv_not_enclosed = (myocardium_overlap / neighborhood_count) < enclosure_threshold

    return AnatomicalPlausibility(
        lv_multiple_components=lv_components > 1,
        rv_multiple_components=rv_components > 1,
        lv_not_enclosed_by_myocardium=lv_not_enclosed,
    )
