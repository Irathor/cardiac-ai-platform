"""Real Grad-CAM explainability over the two trained image models.

Both variants below are genuine gradient-based attribution computed on the
model's own activations/gradients — there is no fabricated/visual-only
heatmap anywhere in this module (see EPIC-1's acceptance criteria and
`docs/clinical-limitations.md`'s "no inventarnos nada" ethic).

Segmentation (U-Net) uses **Seg-Grad-CAM** (Vinogradova et al. 2020,
"Towards Interpretable Semantic Segmentation via Gradient-weighted Class
Activation Mapping"), not classic Grad-CAM, because the U-Net has no single
scalar class logit to backpropagate from — its output is a per-pixel
prediction. Seg-Grad-CAM adapts the method by backpropagating from the sum
of the target class's logits, restricted to the pixels the model itself
predicted as that class, instead of a single scalar. Once that scalar
exists, the rest is standard Grad-CAM (global-average-pooled gradients as
per-channel weights, weighted combination of an intermediate conv layer's
activations, ReLU, upsample to input resolution).

Classification (CNN3D) uses classic 3D Grad-CAM: backpropagate from the
target class's logit (a true scalar, no adaptation needed), hook the last
conv block before global pooling.

Layer choice (verified empirically against the real trained architectures,
not guessed — see the DEFAULT_* constants below):

- U-Net: `model.1.submodule.2.1`, the last decoder `ResidualUnit` one stage
  before the final output projection. At (16, 112, 112) for a 224x224
  input, it is the deepest decoder layer that still carries a wide-enough
  channel dimension (16) to combine into a meaningful heatmap — the very
  last block (`model.2.1`) already collapses to `out_channels=4` (one
  channel per segmentation class), which is not a useful Grad-CAM target
  (weighting 4 near-final logit-like channels degenerates towards the
  logits themselves rather than an intermediate spatial representation).
- CNN3D: `features.3.2`, the ReLU activation of the last (4th) conv block
  in `CompactCNN3D.features`, before its `MaxPool3d` — the standard "last
  conv layer before pooling" Grad-CAM target, with 128 channels.

CNN3D input note: the model's 2-channel input (ED and ES cardiac phases
stacked, see `classification_dataset.py`) is mixed together by the very
first `Conv3d`, so every activation from `features.3` onward already
combines information from both phases per output channel — there is no
principled way to attribute a downstream activation back to "only ED" or
"only ES" without re-deriving per-channel provenance through 4
convolutions, which Grad-CAM's method does not support. The attribution
map this module returns is therefore a single combined (X, Y, Z) volume
that explains the prediction using both phases jointly, not two separate
per-phase maps — this is documented here rather than silently assumed.
"""
from dataclasses import dataclass

import nibabel as nib
import numpy as np
import torch
import torch.nn.functional as F

from ..labels import DEFAULT_LABELS
from .preprocessing import DEFAULT_SLICE_SIZE, DEFAULT_TARGET_SPACING_XY, center_crop_or_pad, normalize_intensity, resample_slice_xy

DEFAULT_UNET_GRADCAM_LAYER = "model.1.submodule.2.1"
DEFAULT_CNN3D_GRADCAM_LAYER = "features.3.2"

STRUCTURE_LABELS = {
    "LV": DEFAULT_LABELS.left_ventricle_cavity,
    "RV": DEFAULT_LABELS.right_ventricle_cavity,
    "MYO": DEFAULT_LABELS.myocardium,
}


class NoActivationForClassError(ValueError):
    """The model predicted zero pixels of the requested class anywhere in
    the image, so there is nothing to backpropagate a class-restricted
    Seg-Grad-CAM score from."""


def get_layer(model: torch.nn.Module, layer_name: str) -> torch.nn.Module:
    modules = dict(model.named_modules())
    if layer_name not in modules:
        raise KeyError(f"no layer named {layer_name!r} in model — available names include {list(modules)[:10]}...")
    return modules[layer_name]


class _ActivationsAndGradients:
    """Hooks a single layer to capture its forward activations and the
    gradients that flow back into them on the next `.backward()` call."""

    def __init__(self, layer: torch.nn.Module) -> None:
        self.activations: torch.Tensor | None = None
        self.gradients: torch.Tensor | None = None
        # Hooking an in-place ReLU (both models use `inplace=True` for
        # memory savings — see models.py) makes PyTorch's autograd refuse
        # a full_backward_hook on it ("Output 0 of BackwardHookFunction is
        # a view and is being modified inplace"), because it mutates the
        # very tensor the hook needs to keep a stable reference to.
        # Disabling in-place-ness only for the hooked layer, only while the
        # hook is attached, is numerically identical (ReLU(x) either way)
        # and sidesteps the autograd restriction without touching the
        # model's normal training/inference behavior.
        self._layer = layer
        self._restore_inplace = getattr(layer, "inplace", False) is True
        if self._restore_inplace:
            layer.inplace = False
        self._forward_handle = layer.register_forward_hook(self._save_activation)
        self._backward_handle = layer.register_full_backward_hook(self._save_gradient)

    def _save_activation(self, module: torch.nn.Module, inputs: tuple, output: torch.Tensor) -> None:
        self.activations = output

    def _save_gradient(self, module: torch.nn.Module, grad_input: tuple, grad_output: tuple) -> None:
        self.gradients = grad_output[0]

    def remove(self) -> None:
        self._forward_handle.remove()
        self._backward_handle.remove()
        if self._restore_inplace:
            self._layer.inplace = True


def _normalize_cam(cam: torch.Tensor) -> np.ndarray:
    cam = F.relu(cam)
    array = cam.detach().cpu().numpy()
    minimum = array.min()
    array = array - minimum
    maximum = array.max()
    if maximum > 0:
        array = array / maximum
    return array.astype(np.float32)


@dataclass(frozen=True)
class SegGradCamResult:
    structure: str
    target_label: int
    attribution: np.ndarray  # (H, W), normalized to [0, 1]
    layer_name: str
    predicted_pixel_count: int


def seg_grad_cam(
    model: torch.nn.Module,
    image: torch.Tensor,
    structure: str,
    *,
    layer_name: str = DEFAULT_UNET_GRADCAM_LAYER,
) -> SegGradCamResult:
    """Seg-Grad-CAM for one segmentation structure (see module docstring).

    `image` must be a single (1, 1, H, W) tensor already preprocessed the
    same way `segmentation_validation.predict_volume` preprocesses slices.
    """
    if structure not in STRUCTURE_LABELS:
        raise ValueError(f"unknown structure {structure!r}, expected one of {list(STRUCTURE_LABELS)}")
    target_label = STRUCTURE_LABELS[structure]

    layer = get_layer(model, layer_name)
    hooks = _ActivationsAndGradients(layer)
    try:
        model.zero_grad(set_to_none=True)
        logits = model(image)  # (1, C, H, W)
        predicted = logits.argmax(dim=1)  # (1, H, W)
        class_mask = (predicted == target_label).float()
        predicted_pixel_count = int(class_mask.sum().item())
        if predicted_pixel_count == 0:
            raise NoActivationForClassError(
                f"model predicted zero pixels of structure {structure!r} (label {target_label}) — "
                "nothing to attribute Seg-Grad-CAM from for this image"
            )

        score = (logits[:, target_label, :, :] * class_mask).sum()
        score.backward()

        activations = hooks.activations  # (1, K, h, w)
        gradients = hooks.gradients  # (1, K, h, w)
        weights = gradients.mean(dim=(2, 3), keepdim=True)  # (1, K, 1, 1)
        cam = (weights * activations).sum(dim=1, keepdim=True)  # (1, 1, h, w)
        cam = F.interpolate(cam, size=image.shape[-2:], mode="bilinear", align_corners=False)
        attribution = _normalize_cam(cam.squeeze(0).squeeze(0))
    finally:
        hooks.remove()

    return SegGradCamResult(
        structure=structure,
        target_label=target_label,
        attribution=attribution,
        layer_name=layer_name,
        predicted_pixel_count=predicted_pixel_count,
    )


def seg_grad_cam_all_structures(
    model: torch.nn.Module, image: torch.Tensor, *, layer_name: str = DEFAULT_UNET_GRADCAM_LAYER
) -> dict[str, SegGradCamResult]:
    """Runs `seg_grad_cam` for every structure the model predicted at least
    one pixel of; structures with zero predicted pixels are silently
    skipped (nothing genuine to attribute) rather than raising."""
    results: dict[str, SegGradCamResult] = {}
    for structure in STRUCTURE_LABELS:
        try:
            results[structure] = seg_grad_cam(model, image, structure, layer_name=layer_name)
        except NoActivationForClassError:
            continue
    return results


def load_single_slice_tensor(
    image_path: str,
    slice_index: int,
    *,
    target_spacing_xy: tuple[float, float] = DEFAULT_TARGET_SPACING_XY,
    target_size: tuple[int, int] = DEFAULT_SLICE_SIZE,
    device: torch.device | None = None,
) -> torch.Tensor:
    """Loads and preprocesses exactly one real slice of a real ACDC NIfTI
    volume, using the identical preprocessing `segmentation_validation.
    predict_volume` applies per-slice, so Grad-CAM sees the model's actual
    working input rather than a re-derived approximation of it."""
    image_nii = nib.load(image_path)
    spacing_xy = image_nii.header.get_zooms()[:2]
    image_slice = np.asarray(image_nii.dataobj[:, :, slice_index], dtype=np.float32)
    image_slice, _ = resample_slice_xy(image_slice, None, spacing_xy, target_spacing_xy)
    image_slice = center_crop_or_pad(image_slice, target_size, pad_value=0.0)
    image_slice = normalize_intensity(image_slice)
    tensor = torch.from_numpy(image_slice).unsqueeze(0).unsqueeze(0)  # (1, 1, H, W)
    return tensor.to(device) if device is not None else tensor


@dataclass(frozen=True)
class ClassificationGradCamResult:
    predicted_class_index: int
    target_class_index: int
    attribution: np.ndarray  # (X, Y, Z), normalized to [0, 1], combined across ED/ES (see module docstring)
    layer_name: str


def grad_cam_3d(
    model: torch.nn.Module,
    volume: torch.Tensor,
    *,
    target_class_index: int | None = None,
    layer_name: str = DEFAULT_CNN3D_GRADCAM_LAYER,
) -> ClassificationGradCamResult:
    """Classic 3D Grad-CAM over the CompactCNN3D classifier.

    `volume` must be a single (1, 2, X, Y, Z) tensor (ED/ES channels
    stacked), preprocessed the same way `AcdcVolumeDataset` preprocesses
    its items. If `target_class_index` is None, explains the model's own
    predicted class.
    """
    layer = get_layer(model, layer_name)
    hooks = _ActivationsAndGradients(layer)
    try:
        model.zero_grad(set_to_none=True)
        logits = model(volume)  # (1, num_classes)
        predicted_class_index = int(logits.argmax(dim=1).item())
        target = predicted_class_index if target_class_index is None else target_class_index

        score = logits[0, target]
        score.backward()

        activations = hooks.activations  # (1, K, d, h, w)
        gradients = hooks.gradients  # (1, K, d, h, w)
        weights = gradients.mean(dim=(2, 3, 4), keepdim=True)  # (1, K, 1, 1, 1)
        cam = (weights * activations).sum(dim=1, keepdim=True)  # (1, 1, d, h, w)
        cam = F.interpolate(cam, size=volume.shape[-3:], mode="trilinear", align_corners=False)
        attribution = _normalize_cam(cam.squeeze(0).squeeze(0))
    finally:
        hooks.remove()

    return ClassificationGradCamResult(
        predicted_class_index=predicted_class_index,
        target_class_index=target,
        attribution=attribution,
        layer_name=layer_name,
    )
