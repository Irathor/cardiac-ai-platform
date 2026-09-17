"""Thin HTTP client for the two real-time inference endpoints
(`POST /inference/classify`, `POST /inference/segment`) exposed by
`ml/scripts/training_runner_service.py` (see docs/dl-training-runner.md) —
the same host-side GPU bridge `app.services.training_service.execute_dl_training`
already uses to launch training jobs, reused here for a single forward pass
instead of a whole training run.

Why the runner and not in-process inference inside the containers: this
inference always requires a real GPU (see
cardiac_ai_ml.dl.inference._require_cuda_device — no silent CPU fallback,
ever), and the worker/backend containers have no GPU passthrough and were
deliberately never given torch/monai at all (see backend/pyproject.toml).
So both real-time `AIAnalysis` classification (app.services.analysis_service)
and real-time auto-segmentation (app.services.auto_segmentation_service)
reach the same host-side, GPU-equipped bridge training already uses, rather
than trying (and failing, or silently degrading) to run inference in a
container with no GPU.

Both a classification request and a segmentation request need to hand the
runner a real NIfTI file it can read directly off disk (nibabel/torch on the
host side) — the containers can't just POST the bytes over HTTP and have the
runner operate purely in-memory the way training results are read back,
because the runner process is not a WSGI app parsing multipart uploads, it's
the same stdlib-only `http.server` used for training (see that module's own
docstring for why it stays dependency-light). So the containers stage the
raw series bytes onto the shared `./data` bind mount (the same mount
training already reads/writes through) under `tmp/inference/`, tell the
runner the path *relative to* that shared root, and clean the staged file up
again once the call returns (success or failure) — nothing is left behind.
"""
import base64
import uuid
from pathlib import Path

import httpx
import numpy as np

from app.core.config import get_settings
from app.core.metrics import observe_inference

# Generous but finite — covers a cold model-load (first inference call after
# the runner starts) plus one real forward pass; a live analysis/
# auto-segmentation is already off the request/response path (Celery worker
# for AIAnalysis; a plain endpoint for auto-segmentation that a clinician
# explicitly triggers and expects to wait a few seconds for), so this being
# a blocking call is fine — see docs/epics/EPIC-2-servir-modelos-reales-inferencia.md.
_INFERENCE_TIMEOUT_S = 120.0


class InferenceRunnerError(RuntimeError):
    """Raised for anything that stops a real-time inference call from
    completing — unreachable runner, no checkpoint on the host yet, a bad
    input file, or the inference subprocess itself failing. Always caught by
    the caller (app.services.analysis_service.execute_analysis /
    app.services.auto_segmentation_service.generate_auto_segmentation) and
    turned into a clean failure — the runner being off is an expected,
    documented manual-prerequisite failure mode (see
    docs/dl-training-runner.md), never something that should crash a Celery
    task or hang a request."""


def _tmp_inference_dir(data_root: str) -> Path:
    tmp_dir = Path(data_root) / "tmp" / "inference"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir


def _stage_bytes_for_runner(data_root: str, file_bytes: bytes) -> tuple[Path, str]:
    """Returns (absolute path as seen from inside this container, path
    relative to data_root — what the runner needs, since its own DATA_ROOT
    is the host's view of this same ./data directory)."""
    relative_path = f"tmp/inference/{uuid.uuid4()}.nii.gz"
    absolute_path = Path(data_root) / relative_path
    _tmp_inference_dir(data_root)
    absolute_path.write_bytes(file_bytes)
    return absolute_path, relative_path


def _cleanup_staged_file(absolute_path: Path) -> None:
    absolute_path.unlink(missing_ok=True)


def _post(path: str, payload: dict) -> dict:
    settings = get_settings()
    try:
        response = httpx.post(f"{settings.training_runner_url}{path}", json=payload, timeout=_INFERENCE_TIMEOUT_S)
    except httpx.HTTPError as exc:
        raise InferenceRunnerError(
            f"could not reach the DL training runner at {settings.training_runner_url} "
            f"(is it running? see docs/dl-training-runner.md): {exc}"
        ) from exc
    if response.status_code != 200:
        raise InferenceRunnerError(f"DL training runner returned {response.status_code}: {response.text}")
    return response.json()


def classify_cnn3d(*, ed_bytes: bytes, es_bytes: bytes) -> dict:
    """Returns {"predicted_class": str, "probabilities": dict[str, float],
    "gradcam_attribution": np.ndarray | None, "gradcam_layer_name": str | None,
    "gradcam_error": str | None} from a real forward pass of the production
    CNN3D checkpoint, run on the host GPU runner.

    EPIC-3: the runner's `_run_classify` computes Grad-CAM in the same pass
    as the classification (see docs/epics/EPIC-3-gradcam-integrado-flujo-servido.md)
    and, on success, includes `gradcam_attribution_base64` (float32
    C-contiguous bytes) / `gradcam_attribution_shape` / `gradcam_layer_name`
    in the JSON — decoded here with the exact same
    `np.frombuffer(...).reshape(...)` pattern `segment_unet` already uses for
    `mask_base64`/`mask_shape`. If Grad-CAM itself failed (classification
    still succeeded), those three keys are absent and `gradcam_error` carries
    the reason instead — both are optional, never required, on the wire.
    """
    settings = get_settings()
    ed_abs, ed_rel = _stage_bytes_for_runner(settings.data_root, ed_bytes)
    es_abs, es_rel = _stage_bytes_for_runner(settings.data_root, es_bytes)
    try:
        with observe_inference("cnn3d"):
            body = _post("/inference/classify", {"ed_relative_path": ed_rel, "es_relative_path": es_rel})
    finally:
        _cleanup_staged_file(ed_abs)
        _cleanup_staged_file(es_abs)

    result = {
        "predicted_class": body["predicted_class"],
        "probabilities": body["probabilities"],
    }
    gradcam_base64 = body.get("gradcam_attribution_base64")
    if gradcam_base64 is not None:
        raw = base64.b64decode(gradcam_base64)
        attribution = np.frombuffer(raw, dtype=np.float32).reshape(body["gradcam_attribution_shape"])
        result["gradcam_attribution"] = attribution
        result["gradcam_layer_name"] = body.get("gradcam_layer_name")
        result["gradcam_error"] = None
    else:
        result["gradcam_attribution"] = None
        result["gradcam_layer_name"] = None
        result["gradcam_error"] = body.get("gradcam_error")
    return result


def segment_unet(*, image_bytes: bytes) -> tuple[np.ndarray, float, float, float]:
    """Returns (predicted label mask, voxel_spacing_x_mm, voxel_spacing_y_mm,
    voxel_spacing_z_mm) from a real forward pass of the production U-Net
    checkpoint, run on the host GPU runner. The mask comes back base64-
    encoded in the JSON response body (small enough — a few hundred KB for
    one series — to not warrant its own file-based round trip through the
    shared mount, unlike the input image)."""
    settings = get_settings()
    image_abs, image_rel = _stage_bytes_for_runner(settings.data_root, image_bytes)
    try:
        with observe_inference("unet"):
            body = _post("/inference/segment", {"image_relative_path": image_rel})
    finally:
        _cleanup_staged_file(image_abs)

    raw = base64.b64decode(body["mask_base64"])
    mask = np.frombuffer(raw, dtype=np.int16).reshape(body["mask_shape"]).astype(np.int32)
    return (
        mask,
        float(body["voxel_spacing_x_mm"]),
        float(body["voxel_spacing_y_mm"]),
        float(body["voxel_spacing_z_mm"]),
    )
