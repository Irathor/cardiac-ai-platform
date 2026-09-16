"""Real (non-smoke) tests for Grad-CAM/Seg-Grad-CAM explainability.

Uses small toy models rather than the full trained checkpoints, so these
tests are fast and don't depend on `data/models/*.pt` being present — but
the property being tested (attribution maps change meaningfully with the
input, and differ per target class/structure) is the same real Seg-Grad-CAM
math the offline showcase script (`ml/scripts/run_explainability_showcase.py`)
runs against the real checkpoints; see that script's own printed output for
the real-checkpoint numbers.
"""
import numpy as np
import pytest
import torch
from torch import nn

from cardiac_ai_ml.dl.explainability import (
    NoActivationForClassError,
    grad_cam_3d,
    seg_grad_cam,
    seg_grad_cam_all_structures,
)
from cardiac_ai_ml.dl.models import build_cnn3d

QUADRANT_SIZE = 32


class ToySegNet(nn.Module):
    """Small 2-layer conv net — enough capacity to learn a real (if toy)
    per-pixel classification task, unlike a single linear layer."""

    def __init__(self) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(1, 8, kernel_size=3, padding=1)
        self.relu = nn.ReLU()
        self.conv2 = nn.Conv2d(8, 4, kernel_size=3, padding=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv2(self.relu(self.conv1(x)))


def _quadrant_input(size: int = QUADRANT_SIZE) -> torch.Tensor:
    """4 quadrants at distinct intensities, matched 1:1 with
    `_quadrant_target`'s class layout below."""
    x = torch.zeros(1, 1, size, size)
    half = size // 2
    x[:, :, :half, :half] = 0.9  # top-left
    x[:, :, :half, half:] = 0.6  # top-right
    x[:, :, half:, :half] = 0.3  # bottom-left
    x[:, :, half:, half:] = 0.1  # bottom-right (stays background)
    return x


def _quadrant_target(size: int = QUADRANT_SIZE) -> torch.Tensor:
    # Label convention matches cardiac_ai_ml.labels.DEFAULT_LABELS exactly
    # (0=background, 1=RV, 2=MYO, 3=LV), so seg_grad_cam's structure names
    # apply directly to this synthetic task.
    y = torch.zeros(1, size, size, dtype=torch.long)
    half = size // 2
    y[:, :half, :half] = 1  # top-left -> RV
    y[:, :half, half:] = 2  # top-right -> MYO
    y[:, half:, :half] = 3  # bottom-left -> LV
    return y


def _train_toy_seg_model() -> tuple[nn.Module, torch.Tensor]:
    """Briefly trains ToySegNet on the quadrant task for real (not just
    random-initialized), so its gradients reflect genuine learned,
    class-discriminative behavior rather than noise."""
    torch.manual_seed(0)
    model = ToySegNet()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.05)
    image = _quadrant_input()
    target = _quadrant_target()
    for _ in range(300):
        optimizer.zero_grad()
        loss = nn.functional.cross_entropy(model(image), target)
        loss.backward()
        optimizer.step()
    model.eval()
    return model, image


def test_toy_model_actually_learned_the_quadrant_task() -> None:
    """Sanity precondition for the tests below: if the toy model didn't
    learn anything real, the Grad-CAM tests that follow would be
    meaningless (there'd be no genuine class-discriminative signal to
    detect)."""
    model, image = _train_toy_seg_model()
    with torch.no_grad():
        predicted = model(image).argmax(dim=1)
    for label in (1, 2, 3):
        assert (predicted == label).sum() > 0, f"model never predicts label {label}"


def test_seg_grad_cam_differs_for_very_different_inputs() -> None:
    """Property-based check: two very different inputs (here, an image and
    its horizontal mirror, which relocates every quadrant) must produce
    different Seg-Grad-CAM attribution maps for the same structure — a
    method that always returns the same heatmap regardless of the input
    would fail this."""
    model, image = _train_toy_seg_model()
    mirrored = torch.flip(image, dims=[3])

    result_original = seg_grad_cam(model, image, "LV", layer_name="conv1")
    result_mirrored = seg_grad_cam(model, mirrored, "LV", layer_name="conv1")

    assert result_original.predicted_pixel_count > 0
    assert result_mirrored.predicted_pixel_count > 0
    assert not np.allclose(result_original.attribution, result_mirrored.attribution, atol=1e-3)


def test_seg_grad_cam_is_class_discriminative() -> None:
    """The attribution map explaining structure A must differ from the map
    explaining structure B on the same input, when the model has real
    discriminative capacity between them (verified in the sanity test
    above) — otherwise Grad-CAM would just be visualizing "generic
    interesting pixels" rather than a genuine per-class explanation."""
    model, image = _train_toy_seg_model()

    result_lv = seg_grad_cam(model, image, "LV", layer_name="conv1")
    result_rv = seg_grad_cam(model, image, "RV", layer_name="conv1")
    result_myo = seg_grad_cam(model, image, "MYO", layer_name="conv1")

    assert not np.allclose(result_lv.attribution, result_rv.attribution, atol=1e-3)
    assert not np.allclose(result_lv.attribution, result_myo.attribution, atol=1e-3)
    assert not np.allclose(result_rv.attribution, result_myo.attribution, atol=1e-3)


def test_seg_grad_cam_all_structures_skips_absent_classes() -> None:
    """A model that never predicts a given structure anywhere should be
    skipped for that structure (nothing genuine to attribute), not raise
    or silently return a meaningless all-zero map."""

    class BackgroundOnly(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            # A real (if functionally irrelevant) conv layer so there's a
            # legitimate layer to hook — its output is discarded, only its
            # gradient (which will be all zero, since it never influences
            # the class-restricted score) matters for this test.
            self.conv1 = nn.Conv2d(1, 8, kernel_size=3, padding=1)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            self.conv1(x)
            batch, _, h, w = x.shape
            logits = torch.zeros(batch, 4, h, w)
            logits[:, 0] = 1.0
            return logits

    model = BackgroundOnly().eval()
    image = _quadrant_input()
    results = seg_grad_cam_all_structures(model, image, layer_name="conv1")
    assert results == {}

    with pytest.raises(NoActivationForClassError):
        seg_grad_cam(model, image, "LV", layer_name="conv1")


def test_grad_cam_3d_differs_for_very_different_inputs() -> None:
    """Same property, in 3D, over the real CompactCNN3D architecture
    (random-initialized weights are enough here: the classifier always has
    a well-defined predicted class to backpropagate from — unlike
    Seg-Grad-CAM, there's no "class predicted nowhere" degenerate case to
    guard against for a plain classification logit)."""
    torch.manual_seed(1)
    model = build_cnn3d(in_channels=2, num_classes=5).eval()

    volume_a = torch.rand(1, 2, 32, 32, 8)
    volume_b = torch.zeros(1, 2, 32, 32, 8)
    volume_b[:, :, :16, :, :] = 1.0

    result_a = grad_cam_3d(model, volume_a)
    result_b = grad_cam_3d(model, volume_b)

    assert result_a.attribution.shape == (32, 32, 8)
    assert not np.allclose(result_a.attribution, result_b.attribution, atol=1e-3)


def test_grad_cam_3d_is_class_discriminative() -> None:
    torch.manual_seed(1)
    model = build_cnn3d(in_channels=2, num_classes=5).eval()
    volume = torch.rand(1, 2, 32, 32, 8)

    result_class_0 = grad_cam_3d(model, volume, target_class_index=0)
    result_class_1 = grad_cam_3d(model, volume, target_class_index=1)

    assert not np.allclose(result_class_0.attribution, result_class_1.attribution, atol=1e-3)
