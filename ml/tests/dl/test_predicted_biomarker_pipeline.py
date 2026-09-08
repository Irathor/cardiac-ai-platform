"""Tests for the predicted-vs-reference biomarker pipeline — tiny synthetic
NIfTI patients, an untrained model, CPU only. Not a real accuracy check
(see docs/ for the real ACDC run); this proves the feature-extraction and
agreement/CV plumbing runs end to end and is internally consistent.
"""
import nibabel as nib
import numpy as np
import pytest
import torch

from cardiac_ai_ml.dl.acdc_dataset import discover_patients
from cardiac_ai_ml.dl.models import build_unet2d
from cardiac_ai_ml.dl.predicted_biomarker_pipeline import (
    FEATURE_NAMES,
    biomarker_agreement_report,
    predicted_biomarker_features,
    reference_biomarker_features,
    run_nearest_centroid_cv_and_external_test,
)

DEVICE = torch.device("cpu")


def _write_nifti(path, array, spacing=(1.5, 1.5, 8.0)):
    affine = np.diag([*spacing, 1.0]).astype(np.float64)
    nib.save(nib.Nifti1Image(array, affine), path)


def _make_patient_dir(root, patient_id: str, group: str, shape=(48, 48, 5)):
    patient_dir = root / patient_id
    patient_dir.mkdir()
    (patient_dir / "Info.cfg").write_text(f"ED: 1\nES: 10\nGroup: {group}\nHeight: 170.0\nWeight: 70.0\nNbFrame: 20\n")
    mask = np.zeros(shape, dtype=np.int16)
    mask[10:20, 10:20, :] = 3  # LV
    mask[25:32, 25:32, :] = 2  # MYO
    mask[35:40, 35:40, :] = 1  # RV
    rng = np.random.default_rng(hash(patient_id) % (2**31))
    for frame in ("frame01", "frame10"):
        _write_nifti(patient_dir / f"{patient_id}_{frame}.nii.gz", rng.integers(0, 500, size=shape).astype(np.int16))
        _write_nifti(patient_dir / f"{patient_id}_{frame}_gt.nii.gz", mask)
    return patient_dir


@pytest.fixture
def synthetic_patients(tmp_path):
    root = tmp_path / "training"
    root.mkdir()
    for group in ("NOR", "MINF", "DCM", "HCM", "RV"):
        for i in range(3):
            _make_patient_dir(root, f"{group}{i}", group)
    return discover_patients(root)


def test_reference_biomarker_features_has_all_expected_keys(synthetic_patients):
    features = reference_biomarker_features(synthetic_patients[0])
    assert set(features) == set(FEATURE_NAMES)
    assert features["LV_EDV"] > 0.0  # the fixture mask has a real LV blob
    # The fixture uses the same mask for both ED and ES frames, so stroke
    # volume (and therefore EF) is exactly 0 — a degenerate but valid value.
    assert features["EJECTION_FRACTION"] == pytest.approx(0.0)


def test_predicted_biomarker_features_runs_with_untrained_model(synthetic_patients):
    model = build_unet2d().to(DEVICE)
    features = predicted_biomarker_features(synthetic_patients[0], model, DEVICE)
    assert set(features) == set(FEATURE_NAMES)
    for value in features.values():
        assert np.isfinite(value)


def test_biomarker_agreement_report_perfect_when_predicted_equals_reference(synthetic_patients):
    reference = {p.patient_id: reference_biomarker_features(p) for p in synthetic_patients}
    # "predicted" == reference here on purpose: proves the agreement report
    # itself is correct (MAE=0, ICC=1) before ever touching a real model.
    report = biomarker_agreement_report(reference, reference)
    assert set(report) == set(FEATURE_NAMES)
    for feature_name in FEATURE_NAMES:
        agreement = report[feature_name]
        assert agreement.mae == pytest.approx(0.0, abs=1e-6)
        assert agreement.rmse == pytest.approx(0.0, abs=1e-6)
        assert agreement.bias == pytest.approx(0.0, abs=1e-6)


def test_biomarker_agreement_report_detects_a_systematic_bias(synthetic_patients):
    reference = {p.patient_id: reference_biomarker_features(p) for p in synthetic_patients}
    # An additive offset (not a multiplicative scale) so this still shows up
    # even for a feature whose reference value happens to be exactly 0 —
    # the fixture's ED/ES masks are identical, so EJECTION_FRACTION is 0 for
    # every synthetic patient, and 0 * anything stays 0.
    biased = {pid: {name: value + 5.0 for name, value in features.items()} for pid, features in reference.items()}
    report = biomarker_agreement_report(biased, reference)
    for feature_name in FEATURE_NAMES:
        assert report[feature_name].bias == pytest.approx(5.0, abs=1e-6)


def test_nearest_centroid_cv_and_external_test_runs_end_to_end(synthetic_patients):
    # stratified_kfold and fit_nearest_centroid both require every one of
    # the 5 diagnosis classes to be represented in every fold's train split
    # — the fixture has 3 patients per class, so CV must run over the full
    # set (a slice like [:10] would drop a class entirely and fail to fit).
    train_patients = synthetic_patients
    test_patients = synthetic_patients[:5]
    features_by_patient = {p.patient_id: reference_biomarker_features(p) for p in synthetic_patients}

    result = run_nearest_centroid_cv_and_external_test(
        train_patients, test_patients, features_by_patient, features_by_patient, k=3, seed=1
    )
    assert result["k"] == 3
    assert len(result["cv_fold_accuracies"]) == 3
    assert 0.0 <= result["cv_mean_accuracy"] <= 1.0
    assert 0.0 <= result["external_test_accuracy"] <= 1.0
    assert result["external_test_case_count"] == len(test_patients)
