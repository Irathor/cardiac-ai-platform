"""Model factories.

`build_unet2d` uses MONAI's UNet — a proven, well-tested implementation
rather than a hand-rolled one, since the segmentation architecture itself
isn't the novel part here (per-slice 2D U-Net is the established approach
for ACDC's anisotropic voxels — see docs/ or the training script's
docstring for why).

`build_cnn3d` is a deliberately compact, custom 3D CNN — NOT a large
off-the-shelf 3D ResNet. ACDC has ~100 training patients across 5 classes
(~20 each); a large network would overfit badly on that little data long
before it learned anything generalizable. Heavy dropout + batch norm +
global average pooling (no giant fully-connected head) instead of depth.
"""
import torch
from monai.networks.nets import UNet
from torch import nn

NUM_SEGMENTATION_CLASSES = 4  # background, RV, myocardium, LV — see cardiac_ai_ml.labels
NUM_DIAGNOSIS_CLASSES = 5  # see cardiac_ai_ml.classification.DiagnosisClass


def build_unet2d(
    in_channels: int = 1,
    out_channels: int = NUM_SEGMENTATION_CLASSES,
) -> UNet:
    return UNet(
        spatial_dims=2,
        in_channels=in_channels,
        out_channels=out_channels,
        channels=(16, 32, 64, 128, 256),
        strides=(2, 2, 2, 2),
        num_res_units=2,
        norm="batch",
        dropout=0.1,
    )


class CompactCNN3D(nn.Module):
    """~2.5M parameters — small on purpose (see module docstring)."""

    def __init__(self, in_channels: int = 2, num_classes: int = NUM_DIAGNOSIS_CLASSES, dropout: float = 0.4) -> None:
        super().__init__()

        def block(in_ch: int, out_ch: int) -> nn.Sequential:
            return nn.Sequential(
                nn.Conv3d(in_ch, out_ch, kernel_size=3, padding=1),
                nn.BatchNorm3d(out_ch),
                nn.ReLU(inplace=True),
                nn.MaxPool3d(kernel_size=2, ceil_mode=True),
            )

        self.features = nn.Sequential(
            block(in_channels, 16),
            block(16, 32),
            block(32, 64),
            block(64, 128),
        )
        self.pool = nn.AdaptiveAvgPool3d(1)
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(dropout),
            nn.Linear(128, 64),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        x = self.pool(x)
        return self.classifier(x)


def build_cnn3d(in_channels: int = 2, num_classes: int = NUM_DIAGNOSIS_CLASSES) -> CompactCNN3D:
    return CompactCNN3D(in_channels=in_channels, num_classes=num_classes)
