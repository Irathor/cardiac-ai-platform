"""torch Dataset yielding 2D (image, mask) slice pairs for U-Net training.

Only the ED and ES frames are used (the ones ACDC ships ground-truth masks
for) — every axial slice of both becomes one independent training example.
Deliberately not resampling the z axis (see preprocessing.py's module
docstring): each native slice is one example, never an interpolated one.
"""
from collections.abc import Callable

import nibabel as nib
import numpy as np
import torch
from torch.utils.data import Dataset

from .acdc_dataset import AcdcPatient
from .preprocessing import DEFAULT_SLICE_SIZE, DEFAULT_TARGET_SPACING_XY, center_crop_or_pad, normalize_intensity, resample_slice_xy


class AcdcSliceDataset(Dataset):
    def __init__(
        self,
        patients: list[AcdcPatient],
        *,
        target_spacing_xy: tuple[float, float] = DEFAULT_TARGET_SPACING_XY,
        target_size: tuple[int, int] = DEFAULT_SLICE_SIZE,
        transform: Callable[[np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]] | None = None,
    ) -> None:
        self.target_spacing_xy = target_spacing_xy
        self.target_size = target_size
        self.transform = transform
        self._index: list[tuple[str, str, int]] = []  # (image_path, mask_path, slice_idx)

        for patient in patients:
            for _phase, image_path, mask_path in patient.frame_image_paths():
                n_slices = nib.load(image_path).shape[2]
                self._index.extend((str(image_path), str(mask_path), z) for z in range(n_slices))

    def __len__(self) -> int:
        return len(self._index)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        image_path, mask_path, z = self._index[idx]
        image_nii = nib.load(image_path)
        mask_nii = nib.load(mask_path)

        image_slice = np.asarray(image_nii.dataobj[:, :, z], dtype=np.float32)
        mask_slice = np.asarray(mask_nii.dataobj[:, :, z], dtype=np.int64)
        spacing_xy = image_nii.header.get_zooms()[:2]

        image_slice, mask_slice = resample_slice_xy(image_slice, mask_slice, spacing_xy, self.target_spacing_xy)
        image_slice = center_crop_or_pad(image_slice, self.target_size, pad_value=0.0)
        mask_slice = center_crop_or_pad(mask_slice, self.target_size, pad_value=0)
        image_slice = normalize_intensity(image_slice)

        if self.transform is not None:
            image_slice, mask_slice = self.transform(image_slice, mask_slice)

        image_tensor = torch.from_numpy(image_slice).unsqueeze(0)  # (1, H, W)
        mask_tensor = torch.from_numpy(mask_slice)  # (H, W), class indices
        return image_tensor, mask_tensor
