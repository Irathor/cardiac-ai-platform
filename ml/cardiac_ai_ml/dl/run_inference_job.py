"""CLI entry point the host DL training runner (see
ml/scripts/training_runner_service.py) launches as a short-lived subprocess
to run one real forward pass — CNN3D diagnosis or U-Net segmentation —
against a real checkpoint.

Kept as its own subprocess, mirroring how `train_segmentation.py`/
`train_classification.py` are already launched as subprocesses, rather than
having the always-stdlib-only runner process import `cardiac_ai_ml.dl.inference`
(and therefore torch) directly: the runner's own process must stay startable
with a plain system Python with nothing pip-installed (see
training_runner_service.py's module docstring) — `.venv-dl` (which has
torch/monai) is only ever guaranteed for whatever runs *as* a subprocess.

Always writes a JSON result to --output, even on failure (as
{"error": "<message>"}) — the parent process reads that file rather than
trying to interpret a bare process exit code, so partial/garbled stdout can
never be mistaken for a result.

Usage:
    python -m cardiac_ai_ml.dl.run_inference_job classify \\
        --weights <cnn3d.pt> --ed-image <path> --es-image <path> --output <result.json>
    python -m cardiac_ai_ml.dl.run_inference_job segment \\
        --weights <unet2d.pt> --image <path> --output <result.json>
"""
import argparse
import base64
import json
import sys

import numpy as np

from .explainability import grad_cam_3d
from .inference import (
    build_cnn3d_volume_tensor,
    load_cnn3d_checkpoint,
    load_unet2d_checkpoint,
    predict_diagnosis_from_volume,
    predict_segmentation_mask,
)


def _run_classify(args: argparse.Namespace) -> dict:
    model = load_cnn3d_checkpoint(args.weights)
    device = next(model.parameters()).device
    # Built once and reused for both the classification forward pass and
    # Grad-CAM below (see EPIC-3's contract) — avoids reloading the
    # checkpoint or re-preprocessing the same ED/ES series twice.
    volume_tensor = build_cnn3d_volume_tensor(args.ed_image, args.es_image, device)
    prediction = predict_diagnosis_from_volume(model, volume_tensor)
    result = {"predicted_class": prediction.predicted_class, "probabilities": prediction.probabilities}

    try:
        # target_class_index=None: explains whatever class the model itself
        # predicted, not one imposed from outside.
        gradcam_result = grad_cam_3d(model, volume_tensor, target_class_index=None)
        attribution = np.ascontiguousarray(gradcam_result.attribution, dtype=np.float32)
        result["gradcam_attribution_base64"] = base64.b64encode(attribution.tobytes()).decode("ascii")
        result["gradcam_attribution_shape"] = list(attribution.shape)
        result["gradcam_layer_name"] = gradcam_result.layer_name
    except Exception as exc:  # noqa: BLE001 — a Grad-CAM failure must never
        # fail the classification itself: the prediction above is already
        # valid and useful without its explanation (see EPIC-3's contract,
        # point 4). Only a failure in the classification forward pass
        # itself (above, uncaught here) should still fail the whole
        # subprocess, as before.
        result["gradcam_error"] = f"{type(exc).__name__}: {exc}"

    return result


def _run_segment(args: argparse.Namespace) -> dict:
    model = load_unet2d_checkpoint(args.weights)
    mask, spacing = predict_segmentation_mask(model, args.image)
    return {
        "mask_base64": base64.b64encode(mask.astype("int16").tobytes()).decode("ascii"),
        "mask_shape": list(mask.shape),
        "voxel_spacing_x_mm": spacing.x_mm,
        "voxel_spacing_y_mm": spacing.y_mm,
        "voxel_spacing_z_mm": spacing.z_mm,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="kind", required=True)

    classify_parser = subparsers.add_parser("classify")
    classify_parser.add_argument("--weights", required=True)
    classify_parser.add_argument("--ed-image", required=True)
    classify_parser.add_argument("--es-image", required=True)
    classify_parser.add_argument("--output", required=True)

    segment_parser = subparsers.add_parser("segment")
    segment_parser.add_argument("--weights", required=True)
    segment_parser.add_argument("--image", required=True)
    segment_parser.add_argument("--output", required=True)

    args = parser.parse_args()

    try:
        result = _run_classify(args) if args.kind == "classify" else _run_segment(args)
    except Exception as exc:  # noqa: BLE001 — must always produce a result file the
        # runner can read, even on failure; re-raised after writing so the
        # subprocess's own exit code still reflects the failure too.
        with open(args.output, "w") as f:
            json.dump({"error": f"{type(exc).__name__}: {exc}"}, f)
        raise

    with open(args.output, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    sys.exit(main())
