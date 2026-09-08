"""The genuinely end-to-end, raw-image diagnosis pipeline: a trained U-Net
predicts ED/ES segmentation masks, the same clinical biomarkers the
nearest-centroid classifier already knows how to use (LVEDV, RVEDV, LV
mass, ejection fraction — see cardiac_ai_ml.biomarkers) are computed from
those PREDICTED masks instead of the ground truth, and a nearest-centroid
model is fit and evaluated on them with the same patient-level k-fold
discipline used everywhere else in this project.

This exists to answer one honest question: does the strong biomarker-
classifier result seen with ground-truth masks (see
compare_biomarker_classifier.py) survive when the segmentation step is a
real, imperfect model instead of an oracle? Two things are reported
side by side, not just a final accuracy number:

1. Biomarker agreement (predicted vs. reference masks) via
   `biomarker_metrics` — how much measurement error the segmentation model
   itself introduces into each clinical feature.
2. Classification performance (CV + external test) using ONLY the
   predicted-mask features — the real, deployable number, whatever it
   turns out to be.
"""
from dataclasses import dataclass

import nibabel as nib
import numpy as np
import torch

from ..biomarkers import VoxelSpacing, compute_frame_biomarkers, ejection_fraction_percent
from ..classification import DiagnosisClass
from ..training import TrainingCase, evaluate, fit_nearest_centroid
from .acdc_dataset import AcdcPatient
from .biomarker_metrics import bland_altman, intraclass_correlation, mean_absolute_error, mean_error, pearson_correlation, root_mean_squared_error
from .cross_validation import stratified_kfold
from .fold_stats import summarize
from .preprocessing import DEFAULT_SLICE_SIZE, DEFAULT_TARGET_SPACING_XY
from .segmentation_validation import native_z_spacing_mm, predict_volume

FEATURE_NAMES = ("EJECTION_FRACTION", "LV_EDV", "RV_EDV", "LV_MASS")


def _mask_pair_to_features(ed_mask: np.ndarray, es_mask: np.ndarray, spacing: VoxelSpacing) -> dict[str, float]:
    ed = compute_frame_biomarkers(ed_mask, spacing)
    es = compute_frame_biomarkers(es_mask, spacing)
    return {
        "EJECTION_FRACTION": ejection_fraction_percent(ed.lv_volume_ml, es.lv_volume_ml),
        "LV_EDV": ed.lv_volume_ml,
        "RV_EDV": ed.rv_volume_ml,
        "LV_MASS": ed.myocardial_mass_g,
    }


def load_reference_mask_and_spacing(mask_path: str) -> tuple[np.ndarray, VoxelSpacing]:
    img = nib.load(str(mask_path))
    mask = np.asarray(img.dataobj).astype(np.int16)
    x, y, z = img.header.get_zooms()[:3]
    return mask, VoxelSpacing(x_mm=float(x), y_mm=float(y), z_mm=float(z))


@torch.no_grad()
def predicted_biomarker_features(
    patient: AcdcPatient, model: torch.nn.Module, device: torch.device,
    *, target_spacing_xy: tuple[float, float] = DEFAULT_TARGET_SPACING_XY, target_size: tuple[int, int] = DEFAULT_SLICE_SIZE,
) -> dict[str, float]:
    """Biomarkers computed from the U-Net's own predicted ED/ES masks — the
    features this patient would actually get in a deployed, image-only
    pipeline (no ground truth involved anywhere in this call)."""
    ed_mask = predict_volume(model, str(patient.ed_image_path), device, target_spacing_xy, target_size)
    es_mask = predict_volume(model, str(patient.es_image_path), device, target_spacing_xy, target_size)
    spacing = VoxelSpacing(target_spacing_xy[0], target_spacing_xy[1], native_z_spacing_mm(str(patient.ed_image_path)))
    return _mask_pair_to_features(ed_mask, es_mask, spacing)


def reference_biomarker_features(patient: AcdcPatient) -> dict[str, float]:
    """The same biomarkers computed from the real ground-truth masks — the
    oracle upper bound this pipeline's predicted-mask numbers are measured
    against."""
    ed_mask, spacing = load_reference_mask_and_spacing(str(patient.ed_mask_path))
    es_mask, _ = load_reference_mask_and_spacing(str(patient.es_mask_path))
    return _mask_pair_to_features(ed_mask, es_mask, spacing)


@dataclass(frozen=True)
class BiomarkerAgreement:
    mae: float
    rmse: float
    bias: float
    pearson_r: float
    icc: float
    bland_altman_mean_difference: float
    bland_altman_loa_lower: float
    bland_altman_loa_upper: float


def biomarker_agreement_report(
    predicted_features: dict[str, dict[str, float]], reference_features: dict[str, dict[str, float]]
) -> dict[str, BiomarkerAgreement]:
    """One agreement summary per biomarker, over every patient present in
    both dicts (keyed by patient_id)."""
    patient_ids = sorted(set(predicted_features) & set(reference_features))
    report: dict[str, BiomarkerAgreement] = {}
    for feature_name in FEATURE_NAMES:
        predicted = [predicted_features[pid][feature_name] for pid in patient_ids]
        reference = [reference_features[pid][feature_name] for pid in patient_ids]
        ba = bland_altman(predicted, reference)
        report[feature_name] = BiomarkerAgreement(
            mae=mean_absolute_error(predicted, reference),
            rmse=root_mean_squared_error(predicted, reference),
            bias=mean_error(predicted, reference),
            pearson_r=pearson_correlation(predicted, reference),
            icc=intraclass_correlation(predicted, reference),
            bland_altman_mean_difference=ba.mean_difference,
            bland_altman_loa_lower=ba.limit_of_agreement_lower,
            bland_altman_loa_upper=ba.limit_of_agreement_upper,
        )
    return report


def _cases_from_features(patients: list[AcdcPatient], features_by_patient: dict[str, dict[str, float]]) -> list[TrainingCase]:
    return [TrainingCase(features=features_by_patient[p.patient_id], label=p.diagnosis_class) for p in patients]


def run_nearest_centroid_cv_and_external_test(
    train_patients: list[AcdcPatient], test_patients: list[AcdcPatient],
    train_features_by_patient: dict[str, dict[str, float]], test_features_by_patient: dict[str, dict[str, float]],
    *, k: int = 5, seed: int = 42,
) -> dict:
    """Same methodology as compare_biomarker_classifier.py: k-fold CV over
    `train_patients` (mirroring the CNN3D's own folds when seed/k match),
    then one final model fit on all of them and evaluated once on
    `test_patients` — never touched during fold selection."""
    class_labels = {d.value for d in DiagnosisClass}
    folds = stratified_kfold(train_patients, k=k, seed=seed)

    fold_accuracies = []
    for fold in folds:
        fold_train_cases = _cases_from_features(fold.train, train_features_by_patient)
        fold_test_cases = _cases_from_features(fold.test, train_features_by_patient)
        prototypes = fit_nearest_centroid(fold_train_cases, class_labels)
        result = evaluate(prototypes, fold_test_cases)
        fold_accuracies.append(result.accuracy)

    accuracy_summary = summarize(fold_accuracies)

    final_prototypes = fit_nearest_centroid(_cases_from_features(train_patients, train_features_by_patient), class_labels)
    final_result = evaluate(final_prototypes, _cases_from_features(test_patients, test_features_by_patient))

    return {
        "k": k,
        "cv_fold_accuracies": fold_accuracies,
        "cv_mean_accuracy": accuracy_summary.mean,
        "cv_std_accuracy": accuracy_summary.std,
        "cv_median_accuracy": accuracy_summary.median,
        "external_test_accuracy": final_result.accuracy,
        "external_test_per_class_accuracy": final_result.per_class_accuracy,
        "external_test_case_count": final_result.case_count,
    }
