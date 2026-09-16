"""Loading real trained checkpoints and running a single forward pass — the
serving-time counterpart to `train_segmentation.py`/`train_classification.py`
(which only ever run offline on the host GPU, see docs/dl-training-runner.md).

Always runs on real GPU hardware, deliberately — unlike the training
scripts' own device selection (`"cuda" if torch.cuda.is_available() else
"cpu"`, acceptable there for a quick CPU smoke test, see
ml/tests/dl/test_training_smoke.py), inference through this module never
falls back to CPU silently: a CPU forward pass over these architectures
produces a result indistinguishable in shape from a real one, so silently
serving one would look like a working deployment while quietly running
numerics nobody validated. If CUDA isn't available in the process calling
this (see `_require_cuda_device`), it fails loudly instead.

Model weights are cached in-process per (weights_path, kind) — see
`_load_checkpoint_cached` — since a Celery task or a request handler calling
this repeatedly (e.g. one auto-segmentation per upload) shouldn't re-read and
rebuild the same checkpoint from disk every time.
"""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import torch

from ..biomarkers import VoxelSpacing
from .classification_dataset import DIAGNOSIS_CLASSES, _load_and_prepare_volume
from .models import build_cnn3d, build_unet2d
from .preprocessing import DEFAULT_SLICE_SIZE, DEFAULT_TARGET_SPACING_XY, DEFAULT_VOLUME_SIZE
from .segmentation_validation import native_z_spacing_mm, predict_volume


def _require_cuda_device() -> torch.device:
    """Raises loudly instead of ever silently continuing on CPU — see this
    module's docstring for why. Called once per checkpoint load (see
    `_load_checkpoint_cached`); predict_diagnosis/predict_segmentation_mask
    reuse whatever device the already-loaded model lives on rather than
    re-checking, so a checkpoint successfully loaded onto GPU is never
    second-guessed mid-request."""
    if not torch.cuda.is_available():
        raise RuntimeError(
            "CUDA no disponible — la inferencia requiere GPU real, ver docs/dl-training-runner.md"
        )
    return torch.device("cuda")


@lru_cache(maxsize=4)
def _load_checkpoint_cached(weights_path: str, kind: str) -> torch.nn.Module:
    if kind == "unet2d":
        model = build_unet2d()
    elif kind == "cnn3d":
        model = build_cnn3d()
    else:
        raise ValueError(f"unknown checkpoint kind {kind!r}")

    device = _require_cuda_device()
    state_dict = torch.load(weights_path, map_location=device)
    model.load_state_dict(state_dict)
    model.to(device)
    model.eval()
    return model


def load_unet2d_checkpoint(weights_path: str) -> torch.nn.Module:
    return _load_checkpoint_cached(str(weights_path), "unet2d")


def load_cnn3d_checkpoint(weights_path: str) -> torch.nn.Module:
    return _load_checkpoint_cached(str(weights_path), "cnn3d")


@dataclass(frozen=True)
class Cnn3dDiagnosisPrediction:
    predicted_class: str
    probabilities: dict[str, float]

    @property
    def confidence(self) -> float:
        return self.probabilities[self.predicted_class]


def build_cnn3d_volume_tensor(ed_image_path: str, es_image_path: str, device: torch.device) -> torch.Tensor:
    """Preprocesses one patient's ED+ES pair into the (1, 2, X, Y, Z) tensor
    the CNN3D expects, exposed separately from `predict_diagnosis` so a
    caller that also needs Grad-CAM on the exact same input (see
    `run_inference_job._run_classify`) builds this tensor once and reuses it
    for both the classification forward pass and `explainability.grad_cam_3d`,
    instead of each preprocessing the series from disk on its own."""
    ed_volume = _load_and_prepare_volume(ed_image_path, DEFAULT_TARGET_SPACING_XY, DEFAULT_VOLUME_SIZE)
    es_volume = _load_and_prepare_volume(es_image_path, DEFAULT_TARGET_SPACING_XY, DEFAULT_VOLUME_SIZE)
    return torch.from_numpy(np.stack([ed_volume, es_volume], axis=0)).unsqueeze(0).to(device)


@torch.no_grad()
def predict_diagnosis_from_volume(model: torch.nn.Module, volume_tensor: torch.Tensor) -> Cnn3dDiagnosisPrediction:
    """Same classification forward pass as `predict_diagnosis`, but taking an
    already-preprocessed volume tensor (see `build_cnn3d_volume_tensor`)
    instead of image paths, so callers that need the identical tensor for
    something else too (Grad-CAM) don't preprocess twice."""
    logits = model(volume_tensor)
    probabilities = torch.softmax(logits, dim=1).squeeze(0).cpu().numpy()
    predicted_index = int(probabilities.argmax())
    return Cnn3dDiagnosisPrediction(
        predicted_class=DIAGNOSIS_CLASSES[predicted_index],
        probabilities={
            label: float(p) for label, p in zip(DIAGNOSIS_CLASSES, probabilities, strict=True)
        },
    )


def predict_diagnosis(model: torch.nn.Module, ed_image_path: str, es_image_path: str) -> Cnn3dDiagnosisPrediction:
    """Runs the real CNN3D over one patient's ED+ES pair (raw cine-MRI
    images — no segmentation involved), using the exact same preprocessing
    `AcdcVolumeDataset` uses for training/evaluation (see
    `classification_dataset.py`), just applied to a real uploaded series
    instead of an ACDC dataset path. `model` must already live on a real CUDA
    device (see `load_cnn3d_checkpoint`/`_require_cuda_device`)."""
    device = next(model.parameters()).device
    volume_tensor = build_cnn3d_volume_tensor(ed_image_path, es_image_path, device)
    return predict_diagnosis_from_volume(model, volume_tensor)


@torch.no_grad()
def predict_segmentation_mask(model: torch.nn.Module, image_path: str) -> tuple[np.ndarray, VoxelSpacing]:
    """Runs the real U-Net over one uploaded series, at the model's own
    working resolution (`DEFAULT_TARGET_SPACING_XY`/`DEFAULT_SLICE_SIZE` — see
    `predict_volume`) — returns the predicted (H, W, Z) label mask together
    with the `VoxelSpacing` it was actually predicted at, so biomarkers get
    computed against the mask's real resolution rather than the original
    series' native spacing (the same approach `predicted_biomarker_pipeline.py`
    already uses for offline evaluation). `model` must already live on a real
    CUDA device (see `load_unet2d_checkpoint`/`_require_cuda_device`)."""
    device = next(model.parameters()).device
    mask = predict_volume(model, image_path, device, DEFAULT_TARGET_SPACING_XY, DEFAULT_SLICE_SIZE)
    spacing = VoxelSpacing(
        x_mm=DEFAULT_TARGET_SPACING_XY[0],
        y_mm=DEFAULT_TARGET_SPACING_XY[1],
        z_mm=native_z_spacing_mm(image_path),
    )
    return mask, spacing
