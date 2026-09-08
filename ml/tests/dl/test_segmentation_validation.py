"""Smoke test for the full segmentation validation report — tiny synthetic
NIfTI patients, an untrained model, CPU only. Not a real accuracy check
(see train_segmentation.py for that against real ACDC data); this only
proves the per-patient 3D reconstruction + metric aggregation pipeline runs
end to end and produces a well-formed, internally consistent report.
"""
import nibabel as nib
import numpy as np
import pytest
import torch

from cardiac_ai_ml.dl.acdc_dataset import discover_patients
from cardiac_ai_ml.dl.models import build_unet2d
from cardiac_ai_ml.dl.segmentation_validation import run_full_segmentation_validation

DEVICE = torch.device("cpu")


def _write_nifti(path, array, spacing=(1.5, 1.5, 8.0)):
    affine = np.diag([*spacing, 1.0]).astype(np.float64)
    nib.save(nib.Nifti1Image(array, affine), path)


def _make_patient_dir(root, patient_id: str, group: str, shape=(32, 32, 4)):
    patient_dir = root / patient_id
    patient_dir.mkdir()
    (patient_dir / "Info.cfg").write_text(f"ED: 1\nES: 10\nGroup: {group}\nHeight: 170.0\nWeight: 70.0\nNbFrame: 20\n")
    mask = np.zeros(shape, dtype=np.int16)
    mask[5:10, 5:10, :] = 3  # LV
    mask[15:18, 15:18, :] = 2  # MYO
    mask[20:23, 20:23, :] = 1  # RV
    for frame in ("frame01", "frame10"):
        _write_nifti(patient_dir / f"{patient_id}_{frame}.nii.gz", np.random.randint(0, 500, size=shape).astype(np.int16))
        _write_nifti(patient_dir / f"{patient_id}_{frame}_gt.nii.gz", mask)
    return patient_dir


def test_report_is_well_formed_for_synthetic_patients(tmp_path):
    root = tmp_path / "training"
    root.mkdir()
    for i in range(3):
        _make_patient_dir(root, f"NOR{i}", "NOR")
    patients = discover_patients(root)

    model = build_unet2d().to(DEVICE)
    report = run_full_segmentation_validation(model, patients, DEVICE, n_bootstrap=50)

    assert report["patient_count"] == 3
    assert set(report["structures"]) == {"LV", "RV", "MYO"}
    assert set(report["phases"]) == {"ED", "ES"}
    assert len(report["per_patient"]) == 3

    for structure in report["structures"]:
        for phase in report["phases"]:
            summary = report["aggregate"][structure][phase]
            assert "mean" in summary["dice"]
            assert 0.0 <= summary["dice"]["mean"] <= 1.0
            assert summary["empty_prediction_percent"] >= 0.0

    for key, (low, high) in report["bootstrap_ci_95_dice"].items():
        assert 0.0 <= low <= high <= 1.0, key

    for phase in report["phases"]:
        assert 0.0 <= report["anatomical_violation_rate_percent"][phase] <= 100.0


def test_background_only_model_is_correctly_scored_as_all_empty_predictions(tmp_path):
    """A model that always predicts background everywhere should score
    Dice == 0 and empty_prediction == 100% for every real structure — a
    sanity check that the pipeline reports a known-bad model as bad,
    instead of silently inflating scores."""
    root = tmp_path / "training"
    root.mkdir()
    _make_patient_dir(root, "NOR0", "NOR")
    patients = discover_patients(root)

    class BackgroundOnly(torch.nn.Module):
        def forward(self, images: torch.Tensor) -> torch.Tensor:
            batch, _, h, w = images.shape
            logits = torch.zeros(batch, 4, h, w)
            logits[:, 0] = 1.0  # always predicts class 0 (background)
            return logits

    model = BackgroundOnly().to(DEVICE)
    report = run_full_segmentation_validation(model, patients, DEVICE, n_bootstrap=20)
    for structure in report["structures"]:
        for phase in report["phases"]:
            summary = report["aggregate"][structure][phase]
            assert summary["empty_prediction_percent"] == 100.0
            assert summary["dice"]["mean"] == pytest.approx(0.0, abs=1e-4)
