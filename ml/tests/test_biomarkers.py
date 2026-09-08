"""Biomarker math verified against synthetic volumes with known ground truth
(exact for axis-aligned blocks, analytic-formula-approximate for a sphere) —
this is the Phase 4 requirement from docs/phases.md, done without any real
MRI data or trained model."""
import math

import numpy as np
import pytest

from cardiac_ai_ml.biomarkers import (
    FrameBiomarkers,
    VoxelSpacing,
    compute_frame_biomarkers,
    ejection_fraction_percent,
    label_volume_ml,
    myocardial_mass_g,
    stroke_volume_ml,
    voxel_volume_ml,
)
from cardiac_ai_ml.labels import DEFAULT_LABELS


def test_voxel_volume_ml_isotropic():
    assert voxel_volume_ml(VoxelSpacing(1.0, 1.0, 1.0)) == pytest.approx(0.001)


def test_voxel_volume_ml_anisotropic():
    # 1.5mm x 1.5mm x 8mm slice thickness, a realistic cardiac cine-MRI voxel.
    assert voxel_volume_ml(VoxelSpacing(1.5, 1.5, 8.0)) == pytest.approx(0.018)


def test_voxel_spacing_rejects_non_positive():
    with pytest.raises(ValueError):
        VoxelSpacing(0.0, 1.0, 1.0)
    with pytest.raises(ValueError):
        VoxelSpacing(1.0, -1.0, 1.0)


def _block_mask(shape: tuple[int, int, int], block: tuple[slice, slice, slice], label: int) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    mask[block] = label
    return mask


def test_label_volume_ml_exact_for_axis_aligned_block():
    # A 10x10x10 voxel block at 2mm isotropic spacing has an exact, known volume:
    # 10*10*10 voxels * (2*2*2 mm^3/voxel) = 8000 mm^3 = 8.0 mL. No discretization
    # error is possible here since the block is perfectly voxel-aligned.
    mask = _block_mask((20, 20, 20), (slice(5, 15), slice(5, 15), slice(5, 15)), DEFAULT_LABELS.left_ventricle_cavity)
    spacing = VoxelSpacing(2.0, 2.0, 2.0)
    assert label_volume_ml(mask, DEFAULT_LABELS.left_ventricle_cavity, spacing) == pytest.approx(8.0)


def test_label_volume_ml_ignores_other_labels():
    mask = _block_mask((10, 10, 10), (slice(0, 5), slice(0, 5), slice(0, 5)), DEFAULT_LABELS.myocardium)
    spacing = VoxelSpacing(1.0, 1.0, 1.0)
    assert label_volume_ml(mask, DEFAULT_LABELS.left_ventricle_cavity, spacing) == 0.0


def _sphere_mask(shape: tuple[int, int, int], center: tuple[float, float, float], radius: float, label: int) -> np.ndarray:
    zz, yy, xx = np.indices(shape)
    dist = np.sqrt((xx - center[0]) ** 2 + (yy - center[1]) ** 2 + (zz - center[2]) ** 2)
    mask = np.zeros(shape, dtype=np.uint8)
    mask[dist <= radius] = label
    return mask


def test_label_volume_ml_matches_sphere_formula_within_discretization_tolerance():
    radius_mm = 20.0
    shape = (60, 60, 60)
    center = (30.0, 30.0, 30.0)
    mask = _sphere_mask(shape, center, radius_mm, DEFAULT_LABELS.left_ventricle_cavity)
    spacing = VoxelSpacing(1.0, 1.0, 1.0)

    analytic_ml = (4 / 3 * math.pi * radius_mm**3) / 1000.0
    measured_ml = label_volume_ml(mask, DEFAULT_LABELS.left_ventricle_cavity, spacing)

    assert measured_ml == pytest.approx(analytic_ml, rel=0.03)


def test_myocardial_mass_g_uses_density():
    mask = _block_mask((10, 10, 10), (slice(0, 5), slice(0, 10), slice(0, 10)), DEFAULT_LABELS.myocardium)
    spacing = VoxelSpacing(1.0, 1.0, 1.0)
    volume_ml = label_volume_ml(mask, DEFAULT_LABELS.myocardium, spacing)
    assert myocardial_mass_g(mask, spacing) == pytest.approx(volume_ml * 1.05)
    assert myocardial_mass_g(mask, spacing, density_g_per_ml=1.0) == pytest.approx(volume_ml)


def test_compute_frame_biomarkers_combines_all_structures():
    shape = (20, 20, 20)
    mask = np.zeros(shape, dtype=np.uint8)
    mask[2:6, 2:6, 2:6] = DEFAULT_LABELS.left_ventricle_cavity  # 4^3 = 64 voxels
    mask[8:12, 8:12, 8:12] = DEFAULT_LABELS.right_ventricle_cavity  # 64 voxels
    mask[14:18, 14:18, 14:18] = DEFAULT_LABELS.myocardium  # 64 voxels
    spacing = VoxelSpacing(1.0, 1.0, 1.0)

    result = compute_frame_biomarkers(mask, spacing)

    assert result == FrameBiomarkers(
        lv_volume_ml=pytest.approx(0.064),
        rv_volume_ml=pytest.approx(0.064),
        myocardial_volume_ml=pytest.approx(0.064),
        myocardial_mass_g=pytest.approx(0.064 * 1.05),
    )


def test_compute_frame_biomarkers_rejects_non_3d_mask():
    with pytest.raises(ValueError):
        compute_frame_biomarkers(np.zeros((10, 10)), VoxelSpacing(1.0, 1.0, 1.0))


def test_frame_biomarkers_as_measurements_shape():
    fb = FrameBiomarkers(lv_volume_ml=1.0, rv_volume_ml=2.0, myocardial_volume_ml=3.0, myocardial_mass_g=4.0)
    measurements = fb.as_measurements()
    names = {name for name, _value, _unit in measurements}
    assert names == {"LV_VOLUME", "RV_VOLUME", "MYOCARDIAL_VOLUME", "MYOCARDIAL_MASS"}
    assert ("MYOCARDIAL_MASS", 4.0, "g") in measurements


def test_stroke_volume_and_ejection_fraction_known_values():
    # A textbook-normal example: EDV 120mL, ESV 50mL -> SV 70mL, EF ~58.3%.
    assert stroke_volume_ml(120.0, 50.0) == pytest.approx(70.0)
    assert ejection_fraction_percent(120.0, 50.0) == pytest.approx(58.333, rel=1e-3)


def test_ejection_fraction_zero_edv_is_undefined_not_zero():
    with pytest.raises(ValueError):
        ejection_fraction_percent(0.0, 0.0)
