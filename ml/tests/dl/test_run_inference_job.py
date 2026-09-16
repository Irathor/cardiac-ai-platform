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
import json
import sys

import pytest
import torch

from cardiac_ai_ml.dl import run_inference_job
from cardiac_ai_ml.dl.models import build_unet2d


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
