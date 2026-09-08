"""Cardiac biomarker calculation from a voxel segmentation mask.

Pure numpy — no FastAPI, no Celery, no file I/O (see docs/architecture.md:
this package must stay usable from a notebook or a Celery worker alike).
Callers are responsible for decoding whatever image format they receive
(e.g. NIfTI) into a label array and a voxel spacing before calling in here.
"""
from dataclasses import dataclass

import numpy as np

from .labels import DEFAULT_LABELS, CardiacLabels

MYOCARDIAL_DENSITY_G_PER_ML = 1.05  # standard assumed density of heart muscle


@dataclass(frozen=True)
class VoxelSpacing:
    x_mm: float
    y_mm: float
    z_mm: float

    def __post_init__(self) -> None:
        if self.x_mm <= 0 or self.y_mm <= 0 or self.z_mm <= 0:
            raise ValueError("voxel spacing must be strictly positive in every dimension")


@dataclass(frozen=True)
class FrameBiomarkers:
    """Biomarkers computable from a single 3D segmentation mask (one cardiac phase)."""

    lv_volume_ml: float
    rv_volume_ml: float
    myocardial_volume_ml: float
    myocardial_mass_g: float

    def as_measurements(self) -> list[tuple[str, float, str]]:
        """(name, value, unit) triples — the shape `BiomarkerMeasurement` rows expect."""
        return [
            ("LV_VOLUME", self.lv_volume_ml, "mL"),
            ("RV_VOLUME", self.rv_volume_ml, "mL"),
            ("MYOCARDIAL_VOLUME", self.myocardial_volume_ml, "mL"),
            ("MYOCARDIAL_MASS", self.myocardial_mass_g, "g"),
        ]


def voxel_volume_ml(spacing: VoxelSpacing) -> float:
    """1 mL == 1000 mm^3."""
    return (spacing.x_mm * spacing.y_mm * spacing.z_mm) / 1000.0


def label_volume_ml(mask: np.ndarray, label: int, spacing: VoxelSpacing) -> float:
    voxel_count = int(np.count_nonzero(mask == label))
    return voxel_count * voxel_volume_ml(spacing)


def myocardial_mass_g(
    mask: np.ndarray,
    spacing: VoxelSpacing,
    *,
    labels: CardiacLabels = DEFAULT_LABELS,
    density_g_per_ml: float = MYOCARDIAL_DENSITY_G_PER_ML,
) -> float:
    return label_volume_ml(mask, labels.myocardium, spacing) * density_g_per_ml


def compute_frame_biomarkers(
    mask: np.ndarray,
    spacing: VoxelSpacing,
    *,
    labels: CardiacLabels = DEFAULT_LABELS,
    density_g_per_ml: float = MYOCARDIAL_DENSITY_G_PER_ML,
) -> FrameBiomarkers:
    if mask.ndim != 3:
        raise ValueError(f"expected a 3D label mask, got {mask.ndim}D")
    myocardial_volume = label_volume_ml(mask, labels.myocardium, spacing)
    return FrameBiomarkers(
        lv_volume_ml=label_volume_ml(mask, labels.left_ventricle_cavity, spacing),
        rv_volume_ml=label_volume_ml(mask, labels.right_ventricle_cavity, spacing),
        myocardial_volume_ml=myocardial_volume,
        myocardial_mass_g=myocardial_volume * density_g_per_ml,
    )


def stroke_volume_ml(edv_ml: float, esv_ml: float) -> float:
    return edv_ml - esv_ml


def ejection_fraction_percent(edv_ml: float, esv_ml: float) -> float:
    """EF = (EDV - ESV) / EDV * 100. EDV must be a real, positive volume —
    an empty/absent end-diastolic cavity means EF is undefined, not zero."""
    if edv_ml <= 0:
        raise ValueError("end-diastolic volume must be positive to compute an ejection fraction")
    return stroke_volume_ml(edv_ml, esv_ml) / edv_ml * 100.0
