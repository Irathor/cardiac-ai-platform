"""End-to-end pipeline tests against a synthetic, ACDC-shaped patient
directory (real NIfTI files, fake pixel data) — catches integration bugs in
discovery/loading/preprocessing now, without needing the real dataset."""
import nibabel as nib
import numpy as np
import pytest

from cardiac_ai_ml.dl.acdc_dataset import MissingAcdcDataError, discover_patients
from cardiac_ai_ml.dl.classification_dataset import AcdcVolumeDataset
from cardiac_ai_ml.dl.segmentation_dataset import AcdcSliceDataset


def _write_nifti(path, array, spacing=(1.5, 1.5, 8.0)):
    affine = np.diag([*spacing, 1.0]).astype(np.float64)
    nib.save(nib.Nifti1Image(array, affine), path)


def _make_patient_dir(root, patient_id: str, group: str, shape=(64, 64, 6)):
    patient_dir = root / patient_id
    patient_dir.mkdir()
    (patient_dir / "Info.cfg").write_text(
        f"ED: 1\nES: 10\nGroup: {group}\nHeight: 170.0\nWeight: 70.0\nNbFrame: 20\n"
    )
    ed_image = np.random.randint(0, 500, size=shape).astype(np.int16)
    ed_mask = np.zeros(shape, dtype=np.int16)
    ed_mask[10:20, 10:20, :] = 3
    ed_mask[30:35, 30:35, :] = 2
    ed_mask[40:45, 40:45, :] = 1
    es_image = np.random.randint(0, 500, size=shape).astype(np.int16)
    es_mask = ed_mask.copy()

    _write_nifti(patient_dir / f"{patient_id}_frame01.nii.gz", ed_image)
    _write_nifti(patient_dir / f"{patient_id}_frame01_gt.nii.gz", ed_mask)
    _write_nifti(patient_dir / f"{patient_id}_frame10.nii.gz", es_image)
    _write_nifti(patient_dir / f"{patient_id}_frame10_gt.nii.gz", es_mask)
    return patient_dir


@pytest.fixture
def acdc_training_root(tmp_path):
    root = tmp_path / "training"
    root.mkdir()
    _make_patient_dir(root, "patient001", "NOR")
    _make_patient_dir(root, "patient002", "DCM")
    return root


def test_discover_patients_reads_info_cfg_correctly(acdc_training_root):
    patients = discover_patients(acdc_training_root)
    assert len(patients) == 2
    p1 = next(p for p in patients if p.patient_id == "patient001")
    assert p1.ed_frame == 1
    assert p1.es_frame == 10
    assert p1.group == "NOR"
    assert p1.diagnosis_class == "NORMAL"
    assert p1.height_cm == 170.0


def test_discover_patients_raises_on_missing_directory(tmp_path):
    with pytest.raises(MissingAcdcDataError):
        discover_patients(tmp_path / "does-not-exist")


def test_discover_patients_raises_when_empty(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(MissingAcdcDataError):
        discover_patients(empty)


def test_acdc_slice_dataset_yields_one_item_per_slice_per_frame(acdc_training_root):
    patients = discover_patients(acdc_training_root)
    dataset = AcdcSliceDataset(patients, target_size=(32, 32))
    # 2 patients * 2 frames (ED+ES) * 6 z-slices each = 24
    assert len(dataset) == 24

    image, mask = dataset[0]
    assert image.shape == (1, 32, 32)
    assert mask.shape == (32, 32)
    assert image.dtype.is_floating_point
    assert set(mask.unique().tolist()) <= {0, 1, 2, 3}


def test_acdc_volume_dataset_yields_one_item_per_patient(acdc_training_root):
    patients = discover_patients(acdc_training_root)
    dataset = AcdcVolumeDataset(patients, target_size=(32, 32, 8))
    assert len(dataset) == 2

    volume, label = dataset[0]
    assert volume.shape == (2, 32, 32, 8)  # ED+ES channels
    assert label.item() in range(5)


def test_acdc_volume_dataset_labels_match_diagnosis_class(acdc_training_root):
    from cardiac_ai_ml.dl.classification_dataset import CLASS_TO_INDEX

    patients = discover_patients(acdc_training_root)
    dataset = AcdcVolumeDataset(patients, target_size=(16, 16, 4))
    for i, patient in enumerate(patients):
        _volume, label = dataset[i]
        assert label.item() == CLASS_TO_INDEX[patient.diagnosis_class]


def test_acdc_volume_dataset_augmentation_stays_in_valid_range(acdc_training_root):
    patients = discover_patients(acdc_training_root)
    dataset = AcdcVolumeDataset(patients, target_size=(16, 16, 4), augment=True, seed=1)
    volume, _label = dataset[0]
    assert volume.min() >= 0.0
    assert volume.max() <= 1.0
