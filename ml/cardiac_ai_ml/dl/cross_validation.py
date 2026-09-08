"""Stratified k-fold patient-level splitting for the CNN3D classifier.

With ~100 patients across 5 classes, a single train/val/test split leaves
each test fold with only ~15-20 patients — too few for a trustworthy
accuracy number on its own (a couple of lucky/unlucky cases swing it by
several points). K-fold cross-validation trains k models on k different
splits and reports the mean and spread across all of them instead, which is
the standard, honest way to evaluate a classifier on a dataset this size.
"""
import random
from dataclasses import dataclass

from .acdc_dataset import AcdcPatient


@dataclass(frozen=True)
class Fold:
    fold_index: int
    train: list[AcdcPatient]
    test: list[AcdcPatient]


def stratified_kfold(patients: list[AcdcPatient], k: int = 5, seed: int = 42) -> list[Fold]:
    if k < 2:
        raise ValueError("k must be at least 2")

    by_group: dict[str, list[AcdcPatient]] = {}
    for patient in patients:
        by_group.setdefault(patient.group, []).append(patient)

    rng = random.Random(seed)
    # buckets[fold_index] accumulates this fold's test patients, built by
    # round-robin-assigning each group's shuffled patients across folds so
    # every fold's test set has roughly the same per-class composition.
    buckets: list[list[AcdcPatient]] = [[] for _ in range(k)]
    for group_patients in by_group.values():
        shuffled = list(group_patients)
        rng.shuffle(shuffled)
        for i, patient in enumerate(shuffled):
            buckets[i % k].append(patient)

    folds = []
    for i in range(k):
        test = buckets[i]
        train = [p for j, bucket in enumerate(buckets) if j != i for p in bucket]
        folds.append(Fold(fold_index=i, train=train, test=test))
    return folds
