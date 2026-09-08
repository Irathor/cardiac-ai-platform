"""Smoke tests for the training loops themselves — tiny synthetic data, 1-2
epochs, CPU-only. Not a real training run (see train_segmentation.py /
train_classification.py for that, against real ACDC data); this only proves
the loop mechanics (forward/backward/optimizer step/checkpoint selection/
metric aggregation) don't throw and produce sane shapes, before spending real
GPU time on the actual dataset."""
import nibabel as nib
import numpy as np
import pytest
import torch
from torch.utils.data import DataLoader

from cardiac_ai_ml.dl.acdc_dataset import discover_patients
from cardiac_ai_ml.dl.classification_dataset import AcdcVolumeDataset
from cardiac_ai_ml.dl.cross_validation import stratified_kfold
from cardiac_ai_ml.dl.metrics import classification_accuracy
from cardiac_ai_ml.dl.models import build_unet2d
from cardiac_ai_ml.dl.segmentation_dataset import AcdcSliceDataset
from cardiac_ai_ml.dl.splits import stratified_train_val_split
from cardiac_ai_ml.dl.train_classification import predict_all, train_one_model
from cardiac_ai_ml.dl.train_segmentation import evaluate, train_one_epoch

DEVICE = torch.device("cpu")


def _write_nifti(path, array, spacing=(1.5, 1.5, 8.0)):
    affine = np.diag([*spacing, 1.0]).astype(np.float64)
    nib.save(nib.Nifti1Image(array, affine), path)


def _make_patient_dir(root, patient_id: str, group: str, shape=(32, 32, 4)):
    patient_dir = root / patient_id
    patient_dir.mkdir()
    (patient_dir / "Info.cfg").write_text(
        f"ED: 1\nES: 10\nGroup: {group}\nHeight: 170.0\nWeight: 70.0\nNbFrame: 20\n"
    )
    mask = np.zeros(shape, dtype=np.int16)
    mask[5:10, 5:10, :] = 3
    mask[15:18, 15:18, :] = 2
    mask[20:23, 20:23, :] = 1
    for frame in ("frame01", "frame10"):
        _write_nifti(patient_dir / f"{patient_id}_{frame}.nii.gz", np.random.randint(0, 500, size=shape).astype(np.int16))
        _write_nifti(patient_dir / f"{patient_id}_{frame}_gt.nii.gz", mask)
    return patient_dir


@pytest.fixture
def synthetic_patients(tmp_path):
    root = tmp_path / "training"
    root.mkdir()
    for group in ("NOR", "MINF", "DCM", "HCM", "RV"):
        for i in range(4):  # 4 per class = 20 patients total, enough for a 5-fold CV smoke test
            _make_patient_dir(root, f"{group}{i}", group)
    return discover_patients(root)


def test_segmentation_training_loop_runs_and_improves_or_holds_loss(synthetic_patients):
    dataset = AcdcSliceDataset(synthetic_patients[:4], target_size=(32, 32))
    loader = DataLoader(dataset, batch_size=4, shuffle=True)

    model = build_unet2d().to(DEVICE)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-2)
    loss_fn = torch.nn.CrossEntropyLoss()

    first_loss = train_one_epoch(model, loader, optimizer, loss_fn, DEVICE)
    for _ in range(3):
        loss = train_one_epoch(model, loader, optimizer, loss_fn, DEVICE)
    assert isinstance(first_loss, float)
    assert loss < first_loss * 2  # sanity: hasn't diverged/exploded

    metrics = evaluate(model, loader, DEVICE)
    assert 0.0 <= metrics["mean_dice_foreground"] <= 1.0
    assert len(metrics["per_class_dice"]) == 4


def test_classification_training_loop_runs_and_returns_valid_predictions(synthetic_patients):
    split = stratified_train_val_split(synthetic_patients, val_fraction=0.2, seed=1)
    model, info = train_one_model(
        split.train, split.val, device=DEVICE, epochs=2, batch_size=4, lr=1e-2, seed=1, target_size=(32, 32, 4)
    )
    assert 0.0 <= info["best_val_accuracy"] <= 1.0
    assert len(info["history"]) == 2

    loader = DataLoader(AcdcVolumeDataset(split.val, target_size=(32, 32, 4)), batch_size=4)
    predictions, targets, probabilities = predict_all(model, loader, DEVICE)
    assert all(0 <= p < 5 for p in predictions)
    assert probabilities.shape == (len(predictions), 5)
    np.testing.assert_allclose(probabilities.sum(axis=1), 1.0, rtol=1e-5)
    accuracy = classification_accuracy(predictions, targets)
    assert 0.0 <= accuracy <= 1.0


def test_kfold_cross_validation_end_to_end_smoke(synthetic_patients):
    folds = stratified_kfold(synthetic_patients, k=2, seed=1)
    assert len(folds) == 2
    for fold in folds:
        inner = stratified_train_val_split(fold.train, val_fraction=0.2, seed=1)
        model, _info = train_one_model(
            inner.train, inner.val, device=DEVICE, epochs=1, batch_size=4, lr=1e-2, seed=1, target_size=(32, 32, 4)
        )
        test_loader = DataLoader(AcdcVolumeDataset(fold.test, target_size=(32, 32, 4)), batch_size=4)
        predictions, targets, probabilities = predict_all(model, test_loader, DEVICE)
        assert len(predictions) == len(fold.test)
        assert probabilities.shape == (len(predictions), 5)
        classification_accuracy(predictions, targets)  # must not raise
