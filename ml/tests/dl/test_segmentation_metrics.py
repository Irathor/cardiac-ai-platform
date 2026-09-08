import dataclasses
import json

import numpy as np
import pytest

from cardiac_ai_ml.dl.segmentation_metrics import (
    binary_dice,
    binary_iou,
    check_anatomical_plausibility,
    connected_components_count,
    is_empty_mask,
    relative_volume_error_percent,
    surface_distances,
    voxel_confusion,
    volume_ml,
    volumetric_similarity,
)

SPACING = (1.0, 1.0, 1.0)


def _cube(shape=(10, 10, 10), lo=2, hi=6) -> np.ndarray:
    mask = np.zeros(shape, dtype=bool)
    mask[lo:hi, lo:hi, lo:hi] = True
    return mask


def test_binary_dice_perfect_overlap_is_one():
    cube = _cube()
    assert binary_dice(cube, cube) == pytest.approx(1.0)


def test_binary_dice_no_overlap_is_near_zero():
    a = np.zeros((10, 10, 10), dtype=bool)
    a[0:2, 0:2, 0:2] = True
    b = np.zeros((10, 10, 10), dtype=bool)
    b[8:10, 8:10, 8:10] = True
    assert binary_dice(a, b) < 0.01


def test_binary_dice_both_empty_is_vacuous_match():
    empty = np.zeros((5, 5, 5), dtype=bool)
    assert binary_dice(empty, empty) == 1.0


def test_binary_iou_half_overlap_hand_computed():
    a = np.zeros((10, 1, 1), dtype=bool)
    a[0:6] = True  # voxels 0-5, size 6
    b = np.zeros((10, 1, 1), dtype=bool)
    b[3:9] = True  # voxels 3-8, size 6
    # intersection = {3,4,5} = 3, union = {0..8} = 9
    assert binary_iou(a, b) == pytest.approx(3 / 9, abs=1e-4)


def test_voxel_confusion_hand_computed():
    prediction = np.array([True, True, False, False])
    target = np.array([True, False, True, False])
    result = voxel_confusion(prediction, target)
    # tp=1, fp=1, fn=1, tn=1
    assert result.precision == pytest.approx(0.5)
    assert result.recall == pytest.approx(0.5)
    assert result.specificity == pytest.approx(0.5)


def test_volume_ml_hand_computed():
    mask = np.zeros((10, 10, 10), dtype=bool)
    mask[0:2, 0:2, 0:2] = True  # 8 voxels
    # 1mm^3 voxels -> 8 mm^3 = 0.008 mL
    assert volume_ml(mask, (1.0, 1.0, 1.0)) == pytest.approx(0.008)


def test_volumetric_similarity_perfect_match_is_one():
    cube = _cube()
    assert volumetric_similarity(cube, cube, SPACING) == pytest.approx(1.0)


def test_relative_volume_error_hand_computed():
    target = np.zeros((10, 1, 1), dtype=bool)
    target[0:4] = True  # volume 4
    prediction = np.zeros((10, 1, 1), dtype=bool)
    prediction[0:5] = True  # volume 5
    assert relative_volume_error_percent(prediction, target, SPACING) == pytest.approx(25.0)


def test_relative_volume_error_undefined_for_empty_reference():
    prediction = _cube()
    empty = np.zeros((10, 10, 10), dtype=bool)
    assert relative_volume_error_percent(prediction, empty, SPACING) is None


def test_is_empty_mask():
    assert is_empty_mask(np.zeros((3, 3, 3), dtype=bool))
    assert not is_empty_mask(_cube())


def test_connected_components_count():
    mask = np.zeros((10, 10, 10), dtype=bool)
    mask[0:2, 0:2, 0:2] = True
    mask[8:10, 8:10, 8:10] = True  # a second, disconnected blob
    assert connected_components_count(mask) == 2
    assert connected_components_count(np.zeros((3, 3, 3), dtype=bool)) == 0


def test_surface_distances_perfect_overlap_is_zero():
    cube = _cube()
    result = surface_distances(cube, cube, SPACING)
    assert result.hausdorff_distance_mm == pytest.approx(0.0)
    assert result.hausdorff_distance_95_mm == pytest.approx(0.0)
    assert result.average_symmetric_surface_distance_mm == pytest.approx(0.0)


def test_surface_distances_known_offset_cubes():
    # Two 1-voxel cubes 5mm apart along x, with 1mm isotropic spacing:
    # the (only) surface point of each is exactly 5mm from the other.
    a = np.zeros((10, 1, 1), dtype=bool)
    a[0] = True
    b = np.zeros((10, 1, 1), dtype=bool)
    b[5] = True
    result = surface_distances(a, b, (1.0, 1.0, 1.0))
    assert result.hausdorff_distance_mm == pytest.approx(5.0)
    assert result.average_symmetric_surface_distance_mm == pytest.approx(5.0)


def test_surface_distances_undefined_when_one_mask_empty():
    cube = _cube()
    empty = np.zeros((10, 10, 10), dtype=bool)
    result = surface_distances(cube, empty, SPACING)
    assert result.hausdorff_distance_mm is None
    assert result.hausdorff_distance_95_mm is None
    assert result.average_symmetric_surface_distance_mm is None


def test_anatomical_plausibility_flags_fragmented_lv():
    lv = np.zeros((10, 10, 10), dtype=bool)
    lv[1:3, 1:3, 1:3] = True
    lv[7:9, 7:9, 7:9] = True  # a second disconnected LV blob
    rv = np.zeros((10, 10, 10), dtype=bool)
    myo = np.zeros((10, 10, 10), dtype=bool)
    result = check_anatomical_plausibility(lv, rv, myo)
    assert result.lv_multiple_components
    assert result.any_violation


def test_anatomical_plausibility_accepts_lv_enclosed_by_myocardium():
    lv = np.zeros((10, 10, 10), dtype=bool)
    lv[4:6, 4:6, 4:6] = True
    myo = np.zeros((10, 10, 10), dtype=bool)
    myo[3:7, 3:7, 3:7] = True
    myo[4:6, 4:6, 4:6] = False  # a ring around the LV
    rv = np.zeros((10, 10, 10), dtype=bool)
    result = check_anatomical_plausibility(lv, rv, myo)
    assert not result.lv_not_enclosed_by_myocardium
    assert not result.any_violation


def test_anatomical_plausibility_flags_lv_not_enclosed():
    lv = np.zeros((10, 10, 10), dtype=bool)
    lv[4:6, 4:6, 4:6] = True
    myo = np.zeros((10, 10, 10), dtype=bool)  # no myocardium anywhere near the LV
    rv = np.zeros((10, 10, 10), dtype=bool)
    result = check_anatomical_plausibility(lv, rv, myo)
    assert result.lv_not_enclosed_by_myocardium


def test_anatomical_plausibility_fields_are_json_serializable():
    """Regression test: on this numpy version, np.count_nonzero returns a
    numpy integer, so a naive comparison built from it is numpy.bool_ (which,
    unlike numpy.float64, is NOT a subclass of Python's bool and json.dumps
    rejects outright) rather than a real Python bool. This exact bug crashed
    a real 60-epoch GPU training run at the very last step — saving its own
    metrics file — so every boolean field here must survive a real
    `json.dumps`, not just an isinstance/equality check."""
    lv = np.zeros((10, 10, 10), dtype=bool)
    lv[4:6, 4:6, 4:6] = True
    myo = np.zeros((10, 10, 10), dtype=bool)
    rv = np.zeros((10, 10, 10), dtype=bool)
    result = check_anatomical_plausibility(lv, rv, myo)

    for field in dataclasses.fields(result):
        value = getattr(result, field.name)
        assert type(value) is bool, f"{field.name} is {type(value)}, not a real Python bool"
    assert type(result.any_violation) is bool

    json.dumps(dataclasses.asdict(result) | {"any_violation": result.any_violation})
