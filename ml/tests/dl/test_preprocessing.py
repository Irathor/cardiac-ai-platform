import numpy as np
import pytest

from cardiac_ai_ml.dl.preprocessing import (
    center_crop_or_pad,
    normalize_intensity,
    resample_slice_xy,
    resample_volume_isotropic_inplane_fixed_z,
)


def test_resample_slice_xy_same_spacing_keeps_shape():
    image = np.random.rand(100, 100).astype(np.float32)
    mask = np.zeros((100, 100), dtype=np.int64)
    mask[40:60, 40:60] = 1

    resampled_image, resampled_mask = resample_slice_xy(image, mask, (1.25, 1.25), (1.25, 1.25))

    assert resampled_image.shape == (100, 100)
    assert resampled_mask.shape == (100, 100)


def test_resample_slice_xy_halves_shape_when_spacing_doubles():
    # 200 voxels at 1.0mm spacing covers the same physical extent as
    # 100 voxels at 2.0mm — resampling to the coarser target should roughly
    # halve the pixel count.
    image = np.random.rand(200, 200).astype(np.float32)
    resampled_image, _ = resample_slice_xy(image, None, (1.0, 1.0), (2.0, 2.0))
    assert resampled_image.shape == (100, 100)


def test_resample_slice_xy_preserves_mask_labels_exactly():
    # Nearest-neighbor interpolation for masks must never invent a label
    # value that wasn't in the original mask (unlike bilinear, which would
    # blend label 1 and label 3 into a fictitious "2" at edges).
    mask = np.zeros((50, 50), dtype=np.int64)
    mask[10:20, 10:20] = 3
    _, resampled_mask = resample_slice_xy(np.zeros((50, 50), dtype=np.float32), mask, (1.0, 1.0), (0.7, 0.7))
    assert set(np.unique(resampled_mask)) <= {0, 3}


def test_resample_slice_xy_rejects_non_2d_input():
    with pytest.raises(ValueError):
        resample_slice_xy(np.zeros((10, 10, 10)), None, (1.0, 1.0))


def test_center_crop_or_pad_crops_larger_array():
    array = np.ones((10, 10))
    result = center_crop_or_pad(array, (4, 4))
    assert result.shape == (4, 4)
    assert np.all(result == 1)


def test_center_crop_or_pad_pads_smaller_array():
    array = np.ones((4, 4))
    result = center_crop_or_pad(array, (10, 10), pad_value=-1.0)
    assert result.shape == (10, 10)
    assert result[0, 0] == -1.0
    assert result[5, 5] == 1.0


def test_center_crop_or_pad_is_idempotent_at_target_size():
    array = np.arange(100).reshape(10, 10).astype(np.float32)
    result = center_crop_or_pad(array, (10, 10))
    assert np.array_equal(result, array)


def test_center_crop_or_pad_mixed_crop_and_pad_per_axis():
    array = np.ones((20, 5))
    result = center_crop_or_pad(array, (10, 10))
    assert result.shape == (10, 10)


def test_normalize_intensity_scales_to_unit_range():
    image = np.array([[0.0, 50.0], [100.0, 25.0]], dtype=np.float32)
    normalized = normalize_intensity(image, low_percentile=0, high_percentile=100)
    assert normalized.min() == pytest.approx(0.0, abs=1e-5)
    assert normalized.max() == pytest.approx(1.0, abs=1e-5)


def test_normalize_intensity_clips_outliers():
    image = np.concatenate([np.full(98, 50.0), [0.0, 10000.0]]).reshape(10, 10).astype(np.float32)
    normalized = normalize_intensity(image, low_percentile=1, high_percentile=99)
    # The extreme outlier must be clipped, not left to dominate the scale.
    assert normalized.max() <= 1.0
    assert normalized[normalized < 1.0].std() < 0.5


def test_normalize_intensity_constant_image_does_not_divide_by_zero():
    image = np.full((10, 10), 5.0, dtype=np.float32)
    result = normalize_intensity(image)
    assert np.all(result == 0.0)


def test_resample_volume_isotropic_inplane_fixed_z_produces_target_shape():
    volume = np.random.rand(64, 64, 8).astype(np.float32)
    result = resample_volume_isotropic_inplane_fixed_z(
        volume, spacing=(1.5, 1.5, 10.0), target_spacing_xy=(1.5, 1.5), target_z_slices=16
    )
    assert result.shape == (64, 64, 16)


def test_resample_volume_rejects_non_3d_input():
    with pytest.raises(ValueError):
        resample_volume_isotropic_inplane_fixed_z(np.zeros((10, 10)), spacing=(1.0, 1.0, 1.0))
