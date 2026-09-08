"""Plain numpy/skimage preprocessing for one 2D slice or one 3D volume at a
time — deliberately not MONAI's dictionary-transform pipeline, so in-plane
(x,y) spacing gets resampled to a common resolution while the through-plane
(z) axis is left as the dataset's own native slices, never interpolated into
new ones (see dl/segmentation_dataset.py's module docstring for why).
"""
import numpy as np
from skimage.transform import resize

DEFAULT_TARGET_SPACING_XY = (1.25, 1.25)  # mm — close to ACDC's actual in-plane spacing (1.37-1.875mm)
DEFAULT_SLICE_SIZE = (224, 224)
# z=12 (not a rounder 16) because the real ACDC volumes measured only 7-11
# native slices each — targeting 16 would upsample every single patient by
# 50-100%+ for no benefit; 12 is close to the observed max (11) instead.
DEFAULT_VOLUME_SIZE = (128, 128, 12)


def resample_slice_xy(
    image: np.ndarray,
    mask: np.ndarray | None,
    spacing_xy: tuple[float, float],
    target_spacing_xy: tuple[float, float] = DEFAULT_TARGET_SPACING_XY,
) -> tuple[np.ndarray, np.ndarray | None]:
    if image.ndim != 2:
        raise ValueError(f"expected a 2D slice, got {image.ndim}D")

    scale = (spacing_xy[0] / target_spacing_xy[0], spacing_xy[1] / target_spacing_xy[1])
    out_shape = (max(1, round(image.shape[0] * scale[0])), max(1, round(image.shape[1] * scale[1])))

    resampled_image = resize(
        image, out_shape, order=1, mode="edge", anti_aliasing=True, preserve_range=True
    ).astype(np.float32)
    resampled_mask = None
    if mask is not None:
        resampled_mask = resize(
            mask, out_shape, order=0, mode="edge", anti_aliasing=False, preserve_range=True
        ).astype(mask.dtype)
    return resampled_image, resampled_mask


def center_crop_or_pad(array: np.ndarray, target_size: tuple[int, ...], pad_value: float = 0.0) -> np.ndarray:
    if array.ndim != len(target_size):
        raise ValueError(f"array has {array.ndim} dims but target_size has {len(target_size)}")

    result = array
    # Pad first (any axis that's too small).
    pad_widths = []
    for current, target in zip(result.shape, target_size, strict=True):
        if current < target:
            total = target - current
            pad_widths.append((total // 2, total - total // 2))
        else:
            pad_widths.append((0, 0))
    if any(p != (0, 0) for p in pad_widths):
        result = np.pad(result, pad_widths, mode="constant", constant_values=pad_value)

    # Then center-crop (any axis that's too large).
    slices = []
    for current, target in zip(result.shape, target_size, strict=True):
        if current > target:
            start = (current - target) // 2
            slices.append(slice(start, start + target))
        else:
            slices.append(slice(None))
    return result[tuple(slices)]


def normalize_intensity(image: np.ndarray, low_percentile: float = 1.0, high_percentile: float = 99.0) -> np.ndarray:
    """Percentile-clip then min-max scale to [0, 1] — robust to the small
    number of very bright/dark outlier voxels MRI reconstruction artifacts
    can produce, unlike a plain min/max normalization."""
    lo, hi = np.percentile(image, [low_percentile, high_percentile])
    if hi <= lo:
        return np.zeros_like(image, dtype=np.float32)
    clipped = np.clip(image, lo, hi)
    return ((clipped - lo) / (hi - lo)).astype(np.float32)


def resample_volume_isotropic_inplane_fixed_z(
    volume: np.ndarray,
    spacing: tuple[float, float, float],
    target_spacing_xy: tuple[float, float] = DEFAULT_TARGET_SPACING_XY,
    target_z_slices: int = DEFAULT_VOLUME_SIZE[2],
) -> np.ndarray:
    """Resamples x/y to `target_spacing_xy` slice by slice, then resamples
    the z axis (number of slices) to a fixed count so every patient's volume
    has the same shape for 3D-CNN batching — z is genuinely resampled here
    (unlike the per-slice 2D path) because the classifier needs one fixed
    tensor shape per input, not a variable slice count."""
    if volume.ndim != 3:
        raise ValueError(f"expected a 3D volume, got {volume.ndim}D")

    resampled_slices = [
        resample_slice_xy(volume[:, :, z], None, spacing[:2], target_spacing_xy)[0]
        for z in range(volume.shape[2])
    ]
    xy_resampled = np.stack(resampled_slices, axis=2)

    if xy_resampled.shape[2] == target_z_slices:
        return xy_resampled
    zoom_z = target_z_slices / xy_resampled.shape[2]
    from scipy.ndimage import zoom

    return zoom(xy_resampled, (1.0, 1.0, zoom_z), order=1).astype(np.float32)
