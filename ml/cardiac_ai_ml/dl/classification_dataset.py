"""torch Dataset yielding one fixed-shape 3D volume (ED and ES stacked as 2
channels) plus a diagnosis label per patient — for CNN3D classification
training. Unlike the segmentation dataset, z *is* resampled here to a fixed
slice count, since a CNN classifier needs one consistent tensor shape per
input (see preprocessing.py's resample_volume_isotropic_inplane_fixed_z).
"""
from functools import lru_cache

import nibabel as nib
import numpy as np
import torch
from torch.utils.data import Dataset

from cardiac_ai_ml.classification import DiagnosisClass

from .acdc_dataset import AcdcPatient
from .preprocessing import (
    DEFAULT_TARGET_SPACING_XY,
    DEFAULT_VOLUME_SIZE,
    center_crop_or_pad,
    normalize_intensity,
    resample_volume_isotropic_inplane_fixed_z,
)

DIAGNOSIS_CLASSES: list[str] = [d.value for d in DiagnosisClass]
CLASS_TO_INDEX: dict[str, int] = {label: i for i, label in enumerate(DIAGNOSIS_CLASSES)}


@lru_cache(maxsize=512)
def _load_and_prepare_volume_cached(
    path_str: str,
    target_spacing_xy: tuple[float, float],
    target_size: tuple[int, int, int],
) -> np.ndarray:
    # Resampling is the expensive step and depends only on these arguments,
    # which are identical every epoch/fold a given (patient, phase) is
    # revisited — caching it turns k-fold-cross-validation-times-many-epochs
    # from "resample from disk every time" into "resample once per patient".
    nii = nib.load(path_str)
    volume = np.asarray(nii.dataobj, dtype=np.float32)
    spacing = nii.header.get_zooms()[:3]
    resampled = resample_volume_isotropic_inplane_fixed_z(
        volume, spacing, target_spacing_xy=target_spacing_xy, target_z_slices=target_size[2]
    )
    cropped = center_crop_or_pad(resampled, target_size, pad_value=0.0)
    return normalize_intensity(cropped)


def _load_and_prepare_volume(
    path,
    target_spacing_xy: tuple[float, float],
    target_size: tuple[int, int, int],
) -> np.ndarray:
    # lru_cache returns the same array object on a hit — copy so a caller
    # mutating (e.g. augmenting) its result can never corrupt the cache.
    return _load_and_prepare_volume_cached(str(path), target_spacing_xy, target_size).copy()


def _augment(ed_volume: np.ndarray, es_volume: np.ndarray, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    """Cheap, label-safe augmentations only — no rotation large enough to
    swap which side is which (that would poison RV-vs-LV-derived labels)."""
    if rng.random() < 0.5:
        ed_volume = np.flip(ed_volume, axis=0).copy()
        es_volume = np.flip(es_volume, axis=0).copy()
    if rng.random() < 0.5:
        k = rng.integers(1, 4)
        ed_volume = np.rot90(ed_volume, k=k, axes=(0, 1)).copy()
        es_volume = np.rot90(es_volume, k=k, axes=(0, 1)).copy()
    intensity_scale = rng.uniform(0.9, 1.1)
    intensity_shift = rng.uniform(-0.05, 0.05)
    ed_volume = np.clip(ed_volume * intensity_scale + intensity_shift, 0.0, 1.0)
    es_volume = np.clip(es_volume * intensity_scale + intensity_shift, 0.0, 1.0)
    return ed_volume, es_volume


class AcdcVolumeDataset(Dataset):
    def __init__(
        self,
        patients: list[AcdcPatient],
        *,
        target_spacing_xy: tuple[float, float] = DEFAULT_TARGET_SPACING_XY,
        target_size: tuple[int, int, int] = DEFAULT_VOLUME_SIZE,
        augment: bool = False,
        seed: int = 0,
    ) -> None:
        self.patients = patients
        self.target_spacing_xy = target_spacing_xy
        self.target_size = target_size
        self.augment = augment
        self._rng = np.random.default_rng(seed)

    def __len__(self) -> int:
        return len(self.patients)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        patient = self.patients[idx]
        ed_volume = _load_and_prepare_volume(patient.ed_image_path, self.target_spacing_xy, self.target_size)
        es_volume = _load_and_prepare_volume(patient.es_image_path, self.target_spacing_xy, self.target_size)

        if self.augment:
            ed_volume, es_volume = _augment(ed_volume, es_volume, self._rng)

        volume_tensor = torch.from_numpy(np.stack([ed_volume, es_volume], axis=0))  # (2, X, Y, Z)
        label_tensor = torch.tensor(CLASS_TO_INDEX[patient.diagnosis_class], dtype=torch.long)
        return volume_tensor, label_tensor
