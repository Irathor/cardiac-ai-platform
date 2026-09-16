"""cardiac_ai_ml.dl.run_inference_job — the CLI the host training runner
launches as a subprocess for real-time inference (see
ml/scripts/training_runner_service.py, docs/dl-training-runner.md).

Runs the CLI's `main()` in-process (not a real subprocess — this test suite
only ever runs where `dl` extras are installed at all, see tests/conftest.py;
whether it's actually launched as a subprocess is training_runner_service.py's
own concern, not this module's). Exercises the real "no GPU" failure path for
real (this environment has no CUDA either way) — the "real result written"
path needs a real GPU, see test_inference.py's `requires_cuda` marker.
"""
import argparse
import base64
import json
import sys

import nibabel as nib
import numpy as np
import pytest
import torch

from cardiac_ai_ml.dl import inference, run_inference_job
from cardiac_ai_ml.dl.explainability import DEFAULT_CNN3D_GRADCAM_LAYER
from cardiac_ai_ml.dl.models import build_cnn3d, build_unet2d
from cardiac_ai_ml.dl.preprocessing import DEFAULT_VOLUME_SIZE

requires_cuda = pytest.mark.skipif(not torch.cuda.is_available(), reason="real inference requires a real GPU")


def _write_nifti(path, array, spacing=(1.5, 1.5, 8.0)):
    affine = np.diag([*spacing, 1.0]).astype(np.float64)
    nib.save(nib.Nifti1Image(array.astype(np.float32), affine), path)


def test_segment_job_without_cuda_writes_a_clear_error_and_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    weights_path = tmp_path / "unet2d.pt"
    torch.save(build_unet2d().state_dict(), weights_path)
    output_path = tmp_path / "result.json"
    image_path = tmp_path / "series.nii.gz"
    image_path.write_bytes(b"not read before the CUDA check fails")

    argv = [
        "run_inference_job", "segment",
        "--weights", str(weights_path), "--image", str(image_path), "--output", str(output_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)

    with pytest.raises(RuntimeError, match="CUDA"):
        run_inference_job.main()

    result = json.loads(output_path.read_text())
    assert "CUDA" in result["error"]


@requires_cuda
def test_classify_job_writes_real_gradcam_attribution_alongside_prediction(tmp_path, monkeypatch):
    """EPIC-3: `classify` must compute real Grad-CAM in the same subprocess
    pass as the classification, reusing the same checkpoint/volume, and
    serialize it into the output JSON with the exact contract keys Tali's
    backend decodes (`gradcam_attribution_base64`/`_shape`/`_layer_name`)."""
    weights_path = tmp_path / "cnn3d.pt"
    torch.save(build_cnn3d().state_dict(), weights_path)
    inference._load_checkpoint_cached.cache_clear()

    ed_path = tmp_path / "ed.nii.gz"
    es_path = tmp_path / "es.nii.gz"
    _write_nifti(ed_path, np.random.rand(32, 32, 4) * 500)
    _write_nifti(es_path, np.random.rand(32, 32, 4) * 500)
    output_path = tmp_path / "result.json"

    argv = [
        "run_inference_job", "classify",
        "--weights", str(weights_path), "--ed-image", str(ed_path), "--es-image", str(es_path),
        "--output", str(output_path),
    ]
    monkeypatch.setattr(sys, "argv", argv)

    run_inference_job.main()

    result = json.loads(output_path.read_text())
    assert "predicted_class" in result
    assert "probabilities" in result
    assert "gradcam_error" not in result

    declared_shape = result["gradcam_attribution_shape"]
    assert declared_shape == list(DEFAULT_VOLUME_SIZE)

    attribution = np.frombuffer(
        base64.b64decode(result["gradcam_attribution_base64"]), dtype=np.float32
    ).reshape(declared_shape)
    assert list(attribution.shape) == declared_shape
    assert attribution.min() >= 0.0
    assert attribution.max() <= 1.0 + 1e-6

    assert result["gradcam_layer_name"] == DEFAULT_CNN3D_GRADCAM_LAYER


def test_classify_job_returns_gradcam_error_when_gradcam_computation_fails(tmp_path, monkeypatch):
    """Isolates the Grad-CAM failure path from EPIC-3's contract point 4: a
    broken Grad-CAM computation must not fail the classification itself.
    Doesn't need real CUDA — only the checkpoint loader's own CUDA
    requirement and the `grad_cam_3d` call are mocked out, so this exercises
    the real CNN3D forward pass (on CPU, since no real GPU is required to
    isolate this one behavior) plus the real error-handling branch in
    `_run_classify`."""
    model = build_cnn3d()
    monkeypatch.setattr(run_inference_job, "load_cnn3d_checkpoint", lambda weights_path: model)

    def _broken_grad_cam(*args, **kwargs):
        raise RuntimeError("synthetic grad-cam failure for testing")

    monkeypatch.setattr(run_inference_job, "grad_cam_3d", _broken_grad_cam)

    ed_path = tmp_path / "ed.nii.gz"
    es_path = tmp_path / "es.nii.gz"
    _write_nifti(ed_path, np.random.rand(32, 32, 4) * 500)
    _write_nifti(es_path, np.random.rand(32, 32, 4) * 500)

    args = argparse.Namespace(weights="unused", ed_image=str(ed_path), es_image=str(es_path))
    result = run_inference_job._run_classify(args)

    assert "predicted_class" in result
    assert "probabilities" in result
    assert "gradcam_attribution_base64" not in result
    assert "gradcam_attribution_shape" not in result
    assert "gradcam_layer_name" not in result
    assert result["gradcam_error"] == "RuntimeError: synthetic grad-cam failure for testing"
