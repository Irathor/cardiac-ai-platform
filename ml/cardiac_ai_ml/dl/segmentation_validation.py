"""Assembles the full per-structure, per-phase segmentation validation
report for a trained U-Net: reconstructs each test patient's full ED/ES
volume from the model's per-slice predictions (the exact same preprocessing
`AcdcSliceDataset` uses, so metrics are computed in the model's own working
resolution — see `preprocessing.py`'s module docstring for why z is never
resampled but x/y are), then runs every `segmentation_metrics` function
per structure and aggregates across patients.

Deliberately takes a model + patient list (not pre-computed predictions,
unlike `classification_validation.py`) because reconstructing a full 3D
volume from 2D slice predictions is themselves specific to this evaluation
pass — training itself only ever needs per-slice batches.
"""
import nibabel as nib
import numpy as np
import torch

from ..labels import DEFAULT_LABELS
from .acdc_dataset import AcdcPatient
from .fold_stats import bootstrap_ci, summarize
from .preprocessing import DEFAULT_SLICE_SIZE, DEFAULT_TARGET_SPACING_XY, center_crop_or_pad, normalize_intensity, resample_slice_xy
from .segmentation_metrics import (
    binary_dice,
    binary_iou,
    check_anatomical_plausibility,
    connected_components_count,
    is_empty_mask,
    relative_volume_error_percent,
    surface_distances,
    voxel_confusion,
    volumetric_similarity,
)

STRUCTURES = {"LV": DEFAULT_LABELS.left_ventricle_cavity, "RV": DEFAULT_LABELS.right_ventricle_cavity, "MYO": DEFAULT_LABELS.myocardium}
PHASES = ("ED", "ES")


@torch.no_grad()
def predict_volume(
    model: torch.nn.Module, image_path: str, device: torch.device, target_spacing_xy: tuple[float, float], target_size: tuple[int, int]
) -> np.ndarray:
    """Runs the model slice-by-slice over one full 3D image and stacks the
    argmaxed predictions back into a (H, W, Z) label volume."""
    image_nii = nib.load(image_path)
    spacing_xy = image_nii.header.get_zooms()[:2]
    n_slices = image_nii.shape[2]

    slices = []
    for z in range(n_slices):
        image_slice = np.asarray(image_nii.dataobj[:, :, z], dtype=np.float32)
        image_slice, _ = resample_slice_xy(image_slice, None, spacing_xy, target_spacing_xy)
        image_slice = center_crop_or_pad(image_slice, target_size, pad_value=0.0)
        image_slice = normalize_intensity(image_slice)
        slices.append(image_slice)

    batch = torch.from_numpy(np.stack(slices)).unsqueeze(1).to(device)  # (Z, 1, H, W)
    logits = model(batch)
    predicted = logits.argmax(dim=1).cpu().numpy()  # (Z, H, W)
    return np.moveaxis(predicted, 0, -1)  # (H, W, Z)


def _load_resampled_mask_volume(mask_path: str, target_spacing_xy: tuple[float, float], target_size: tuple[int, int]) -> np.ndarray:
    mask_nii = nib.load(mask_path)
    spacing_xy = mask_nii.header.get_zooms()[:2]
    n_slices = mask_nii.shape[2]

    slices = []
    for z in range(n_slices):
        mask_slice = np.asarray(mask_nii.dataobj[:, :, z], dtype=np.int64)
        _, mask_slice = resample_slice_xy(np.zeros_like(mask_slice, dtype=np.float32), mask_slice, spacing_xy, target_spacing_xy)
        mask_slice = center_crop_or_pad(mask_slice, target_size, pad_value=0)
        slices.append(mask_slice)
    return np.stack(slices, axis=-1)  # (H, W, Z)


def native_z_spacing_mm(image_path: str) -> float:
    return float(nib.load(image_path).header.get_zooms()[2])


def _evaluate_one_phase(
    model: torch.nn.Module, image_path: str, mask_path: str, device: torch.device,
    target_spacing_xy: tuple[float, float], target_size: tuple[int, int],
) -> dict:
    prediction_volume = predict_volume(model, image_path, device, target_spacing_xy, target_size)
    target_volume = _load_resampled_mask_volume(mask_path, target_spacing_xy, target_size)
    spacing = (target_spacing_xy[0], target_spacing_xy[1], native_z_spacing_mm(image_path))

    per_structure = {}
    structure_masks_pred = {}
    for name, label in STRUCTURES.items():
        pred_mask = prediction_volume == label
        target_mask = target_volume == label
        structure_masks_pred[name] = pred_mask
        confusion = voxel_confusion(pred_mask, target_mask)
        distances = surface_distances(pred_mask, target_mask, spacing)
        per_structure[name] = {
            "dice": binary_dice(pred_mask, target_mask),
            "iou": binary_iou(pred_mask, target_mask),
            "precision": confusion.precision,
            "recall": confusion.recall,
            "specificity": confusion.specificity,
            "volumetric_similarity": volumetric_similarity(pred_mask, target_mask, spacing),
            "relative_volume_error_percent": relative_volume_error_percent(pred_mask, target_mask, spacing),
            "hausdorff_distance_mm": distances.hausdorff_distance_mm,
            "hausdorff_distance_95_mm": distances.hausdorff_distance_95_mm,
            "average_symmetric_surface_distance_mm": distances.average_symmetric_surface_distance_mm,
            "empty_prediction": is_empty_mask(pred_mask),
            "empty_target": is_empty_mask(target_mask),
            "connected_components": connected_components_count(pred_mask),
        }

    plausibility = check_anatomical_plausibility(
        structure_masks_pred["LV"], structure_masks_pred["RV"], structure_masks_pred["MYO"]
    )
    return {"structures": per_structure, "anatomical_violation": plausibility.any_violation}


def _aggregate_structure_phase(per_patient_values: list[dict]) -> dict:
    def _numeric_summary(key: str) -> dict | None:
        values = [v[key] for v in per_patient_values if v[key] is not None]
        undefined_count = len(per_patient_values) - len(values)
        if not values:
            return {"undefined_count": undefined_count}
        summary = summarize(values)
        return {
            "mean": summary.mean, "std": summary.std, "median": summary.median,
            "iqr": summary.iqr, "min": summary.minimum, "max": summary.maximum,
            "undefined_count": undefined_count,
        }

    n = len(per_patient_values)
    empty_pred = sum(1 for v in per_patient_values if v["empty_prediction"])
    empty_target = sum(1 for v in per_patient_values if v["empty_target"])
    return {
        "dice": _numeric_summary("dice"),
        "iou": _numeric_summary("iou"),
        "precision": _numeric_summary("precision"),
        "recall": _numeric_summary("recall"),
        "specificity": _numeric_summary("specificity"),
        "volumetric_similarity": _numeric_summary("volumetric_similarity"),
        "relative_volume_error_percent": _numeric_summary("relative_volume_error_percent"),
        "hausdorff_distance_mm": _numeric_summary("hausdorff_distance_mm"),
        "hausdorff_distance_95_mm": _numeric_summary("hausdorff_distance_95_mm"),
        "average_symmetric_surface_distance_mm": _numeric_summary("average_symmetric_surface_distance_mm"),
        "empty_prediction_count": empty_pred,
        "empty_prediction_percent": empty_pred / n * 100.0,
        "empty_target_count": empty_target,
        "empty_target_percent": empty_target / n * 100.0,
        "connected_components_mean": float(np.mean([v["connected_components"] for v in per_patient_values])),
    }


def run_full_segmentation_validation(
    model: torch.nn.Module,
    patients: list[AcdcPatient],
    device: torch.device,
    *,
    target_spacing_xy: tuple[float, float] = DEFAULT_TARGET_SPACING_XY,
    target_size: tuple[int, int] = DEFAULT_SLICE_SIZE,
    n_bootstrap: int = 2000,
    bootstrap_seed: int = 42,
) -> dict:
    model.eval()
    per_patient: dict[str, dict] = {}
    for patient in patients:
        per_patient[patient.patient_id] = {
            "ED": _evaluate_one_phase(model, str(patient.ed_image_path), str(patient.ed_mask_path), device, target_spacing_xy, target_size),
            "ES": _evaluate_one_phase(model, str(patient.es_image_path), str(patient.es_mask_path), device, target_spacing_xy, target_size),
        }

    aggregate: dict[str, dict] = {}
    bootstrap_ci_dice: dict[str, list[float]] = {}
    violation_rate: dict[str, float] = {}
    patient_ids = list(per_patient.keys())

    for phase in PHASES:
        violated = sum(1 for pid in patient_ids if per_patient[pid][phase]["anatomical_violation"])
        violation_rate[phase] = violated / len(patient_ids) * 100.0

    for structure in STRUCTURES:
        aggregate[structure] = {}
        for phase in PHASES:
            values = [per_patient[pid][phase]["structures"][structure] for pid in patient_ids]
            aggregate[structure][phase] = _aggregate_structure_phase(values)

            dice_values = [v["dice"] for v in values]

            def _dice_at_indices(indices: np.ndarray, dice_values: list[float] = dice_values) -> float:
                return float(np.mean([dice_values[i] for i in indices]))

            low, high = bootstrap_ci(len(dice_values), _dice_at_indices, n_resamples=n_bootstrap, seed=bootstrap_seed)
            bootstrap_ci_dice[f"{structure}_{phase}"] = [low, high]

    return {
        "structures": list(STRUCTURES.keys()),
        "phases": list(PHASES),
        "patient_count": len(patients),
        "per_patient": per_patient,
        "aggregate": aggregate,
        "anatomical_violation_rate_percent": violation_rate,
        "bootstrap_ci_95_dice": bootstrap_ci_dice,
    }
