from pathlib import Path

import pytest

from cardiac_ai_ml.dl.acdc_dataset import AcdcPatient
from cardiac_ai_ml.dl.cross_validation import stratified_kfold


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


def test_kfold_every_patient_appears_in_exactly_one_test_fold():
    patients = _all_patients()
    folds = stratified_kfold(patients, k=5)

    all_test_ids = [p.patient_id for fold in folds for p in fold.test]
    assert sorted(all_test_ids) == sorted(p.patient_id for p in patients)
    assert len(all_test_ids) == len(set(all_test_ids))


def test_kfold_train_and_test_never_overlap_within_a_fold():
    folds = stratified_kfold(_all_patients(), k=5)
    for fold in folds:
        train_ids = {p.patient_id for p in fold.train}
        test_ids = {p.patient_id for p in fold.test}
        assert train_ids.isdisjoint(test_ids)


def test_kfold_test_sets_are_stratified_by_group():
    patients = _all_patients()  # 20 per group, 5 groups
    folds = stratified_kfold(patients, k=5)
    for fold in folds:
        groups_in_test = [p.group for p in fold.test]
        # 20 patients per group / 5 folds = 4 per group per fold, every group represented.
        assert set(groups_in_test) == {"NOR", "MINF", "DCM", "HCM", "RV"}
        for group in set(groups_in_test):
            assert groups_in_test.count(group) == 4


def test_kfold_rejects_k_less_than_2():
    with pytest.raises(ValueError):
        stratified_kfold(_all_patients(), k=1)


def test_kfold_is_deterministic_for_a_given_seed():
    patients = _all_patients()
    folds_a = stratified_kfold(patients, k=5, seed=7)
    folds_b = stratified_kfold(patients, k=5, seed=7)
    assert [p.patient_id for p in folds_a[0].test] == [p.patient_id for p in folds_b[0].test]


def test_kfold_different_seeds_usually_differ():
    patients = _all_patients()
    folds_a = stratified_kfold(patients, k=5, seed=1)
    folds_b = stratified_kfold(patients, k=5, seed=2)
    assert [p.patient_id for p in folds_a[0].test] != [p.patient_id for p in folds_b[0].test]
