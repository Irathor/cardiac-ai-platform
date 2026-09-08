from pathlib import Path

import pytest

from cardiac_ai_ml.dl.acdc_dataset import AcdcPatient
from cardiac_ai_ml.dl.splits import stratified_patient_split, stratified_train_val_split


def _make_patients(group: str, count: int) -> list[AcdcPatient]:
    return [
        AcdcPatient(
            patient_id=f"{group}{i}", directory=Path("."), ed_frame=1, es_frame=10,
            group=group, height_cm=170.0, weight_kg=70.0, nb_frame=20,
        )
        for i in range(count)
    ]


def _all_patients() -> list[AcdcPatient]:
    patients = []
    for group in ("NOR", "MINF", "DCM", "HCM", "RV"):
        patients.extend(_make_patients(group, 20))
    return patients


def test_stratified_patient_split_no_overlap_and_covers_everyone():
    patients = _all_patients()
    splits = stratified_patient_split(patients, val_fraction=0.2, test_fraction=0.2)

    all_ids = {p.patient_id for p in splits.train + splits.val + splits.test}
    assert all_ids == {p.patient_id for p in patients}
    train_ids = {p.patient_id for p in splits.train}
    val_ids = {p.patient_id for p in splits.val}
    test_ids = {p.patient_id for p in splits.test}
    assert train_ids.isdisjoint(val_ids)
    assert train_ids.isdisjoint(test_ids)
    assert val_ids.isdisjoint(test_ids)


def test_stratified_patient_split_rejects_invalid_fractions():
    with pytest.raises(ValueError):
        stratified_patient_split(_all_patients(), val_fraction=0.6, test_fraction=0.6)


def test_stratified_train_val_split_no_overlap():
    patients = _all_patients()
    split = stratified_train_val_split(patients, val_fraction=0.2)
    train_ids = {p.patient_id for p in split.train}
    val_ids = {p.patient_id for p in split.val}
    assert train_ids.isdisjoint(val_ids)
    assert train_ids | val_ids == {p.patient_id for p in patients}


def test_stratified_train_val_split_rejects_invalid_fraction():
    with pytest.raises(ValueError):
        stratified_train_val_split(_all_patients(), val_fraction=1.5)
