"""Serving-time inference (cardiac_ai_ml.dl.inference) — real checkpoints
(randomly-initialized, not trained — this only proves the pipeline runs and
produces sane shapes/values, not model accuracy, same convention as
test_training_smoke.py), but genuinely loaded from disk and forward-passed.

Deliberately requires real CUDA for the "happy path" tests (see
inference.py's module docstring: no silent CPU fallback for real inference)
— those are skipped unless a real GPU is present in whatever environment
runs this suite. The "CUDA unavailable raises a clear error" guard test is
NOT skipped: it's the one behavior this module must have everywhere,
GPU-equipped or not.
"""
import nibabel as nib
import numpy as np
import pytest
import torch

from cardiac_ai_ml.dl import inference
from cardiac_ai_ml.dl.models import build_cnn3d, build_unet2d

requires_cuda = pytest.mark.skipif(not torch.cuda.is_available(), reason="real inference requires a real GPU")


def _write_nifti(path, array, spacing=(1.5, 1.5, 8.0)):
    affine = np.diag([*spacing, 1.0]).astype(np.float64)
    nib.save(nib.Nifti1Image(array.astype(np.float32), affine), path)


def test_require_cuda_device_raises_a_clear_error_when_cuda_is_unavailable(monkeypatch):
    """The one guarantee this module makes everywhere: it never silently
    runs inference on CPU."""
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="CUDA"):
        inference._require_cuda_device()


def test_load_checkpoint_raises_instead_of_falling_back_to_cpu(tmp_path, monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    weights_path = tmp_path / "unet2d.pt"
    torch.save(build_unet2d().state_dict(), weights_path)
    inference._load_checkpoint_cached.cache_clear()

    with pytest.raises(RuntimeError, match="CUDA"):
        inference.load_unet2d_checkpoint(str(weights_path))


@requires_cuda
def test_predict_diagnosis_returns_valid_probabilities_from_a_real_cnn3d(tmp_path):
    weights_path = tmp_path / "cnn3d.pt"
    torch.save(build_cnn3d().state_dict(), weights_path)
    inference._load_checkpoint_cached.cache_clear()
    model = inference.load_cnn3d_checkpoint(str(weights_path))

    ed_path = tmp_path / "ed.nii.gz"
    es_path = tmp_path / "es.nii.gz"
    _write_nifti(ed_path, np.random.rand(32, 32, 4) * 500)
    _write_nifti(es_path, np.random.rand(32, 32, 4) * 500)

    prediction = inference.predict_diagnosis(model, str(ed_path), str(es_path))
    assert prediction.predicted_class in prediction.probabilities
    assert sum(prediction.probabilities.values()) == pytest.approx(1.0, abs=1e-4)
    assert prediction.confidence == pytest.approx(max(prediction.probabilities.values()))


@requires_cuda
def test_predict_segmentation_mask_returns_labels_in_the_expected_range(tmp_path):
    weights_path = tmp_path / "unet2d.pt"
    torch.save(build_unet2d().state_dict(), weights_path)
    inference._load_checkpoint_cached.cache_clear()
    model = inference.load_unet2d_checkpoint(str(weights_path))

    image_path = tmp_path / "series.nii.gz"
    _write_nifti(image_path, np.random.rand(40, 40, 6) * 500)

    mask, spacing = inference.predict_segmentation_mask(model, str(image_path))
    assert mask.shape[2] == 6  # z is never resampled — one predicted slice per input slice
    assert set(np.unique(mask)).issubset({0, 1, 2, 3})
    assert (spacing.x_mm, spacing.y_mm) == (1.25, 1.25)
    assert spacing.z_mm == pytest.approx(8.0)
