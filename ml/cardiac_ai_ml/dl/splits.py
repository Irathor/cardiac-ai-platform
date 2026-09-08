"""Patient-level train/val/test splitting, stratified by diagnosis group.

Splitting must happen at the patient level, never the slice/frame level —
splitting slices would let the same patient's anatomy leak across splits
(near-identical neighboring slices ending up in both train and val/test),
inflating validation metrics without the model actually generalizing. This
is the same principle app.services.dataset_service enforces for the
clinical-portal DatasetVersion (see docs/data-dictionary.md), applied here
to the raw ACDC cohort instead.
"""
import random
from dataclasses import dataclass

from .acdc_dataset import AcdcPatient


@dataclass(frozen=True)
class PatientSplits:
    train: list[AcdcPatient]
    val: list[AcdcPatient]
    test: list[AcdcPatient]


@dataclass(frozen=True)
class TrainValSplit:
    train: list[AcdcPatient]
    val: list[AcdcPatient]


def stratified_train_val_split(
    patients: list[AcdcPatient], *, val_fraction: float = 0.15, seed: int = 42
) -> TrainValSplit:
    """Two-way version of stratified_patient_split, for contexts (like one
    cross-validation fold's own train set) that need a val slice for early
    stopping but have no separate outer test set of their own."""
    if not 0 < val_fraction < 1:
        raise ValueError("val_fraction must be in (0, 1)")

    by_group: dict[str, list[AcdcPatient]] = {}
    for patient in patients:
        by_group.setdefault(patient.group, []).append(patient)

    rng = random.Random(seed)
    train: list[AcdcPatient] = []
    val: list[AcdcPatient] = []
    for group_patients in by_group.values():
        shuffled = list(group_patients)
        rng.shuffle(shuffled)
        n = len(shuffled)
        n_val = min(max(1, round(n * val_fraction)), max(0, n - 1))
        val.extend(shuffled[:n_val])
        train.extend(shuffled[n_val:])

    return TrainValSplit(train=train, val=val)


def stratified_patient_split(
    patients: list[AcdcPatient],
    *,
    val_fraction: float = 0.15,
    test_fraction: float = 0.15,
    seed: int = 42,
) -> PatientSplits:
    if not 0 < val_fraction < 1 or not 0 < test_fraction < 1 or val_fraction + test_fraction >= 1:
        raise ValueError("val_fraction and test_fraction must each be in (0, 1) and sum to < 1")

    by_group: dict[str, list[AcdcPatient]] = {}
    for patient in patients:
        by_group.setdefault(patient.group, []).append(patient)

    rng = random.Random(seed)
    train: list[AcdcPatient] = []
    val: list[AcdcPatient] = []
    test: list[AcdcPatient] = []

    for group_patients in by_group.values():
        shuffled = list(group_patients)
        rng.shuffle(shuffled)
        n = len(shuffled)
        n_val = max(1, round(n * val_fraction))
        n_test = max(1, round(n * test_fraction))
        # Never let val+test consume the whole group when n is small.
        n_val = min(n_val, max(0, n - 1))
        n_test = min(n_test, max(0, n - n_val - 1))
        val.extend(shuffled[:n_val])
        test.extend(shuffled[n_val : n_val + n_test])
        train.extend(shuffled[n_val + n_test :])

    return PatientSplits(train=train, val=val, test=test)
