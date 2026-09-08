import pytest

from cardiac_ai_ml.classification import FEATURE_NAMES, classify_with_prototypes
from cardiac_ai_ml.training import (
    EmptyTrainingSetError,
    MissingClassError,
    TrainingCase,
    evaluate,
    fit_nearest_centroid,
)

CLASS_LABELS = {"A", "B"}


def _case(label, ef, lv_edv, rv_edv, lv_mass):
    return TrainingCase(
        features={"EJECTION_FRACTION": ef, "LV_EDV": lv_edv, "RV_EDV": rv_edv, "LV_MASS": lv_mass},
        label=label,
    )


def test_fit_nearest_centroid_computes_the_per_class_mean():
    cases = [
        _case("A", 60.0, 100.0, 100.0, 100.0),
        _case("A", 70.0, 120.0, 120.0, 120.0),
        _case("B", 20.0, 300.0, 100.0, 150.0),
    ]
    prototypes = fit_nearest_centroid(cases, CLASS_LABELS)

    assert prototypes["A"]["EJECTION_FRACTION"] == pytest.approx(65.0)
    assert prototypes["A"]["LV_EDV"] == pytest.approx(110.0)
    assert prototypes["B"]["EJECTION_FRACTION"] == pytest.approx(20.0)
    assert set(prototypes["A"]) == set(FEATURE_NAMES)


def test_fit_nearest_centroid_rejects_empty_training_set():
    with pytest.raises(EmptyTrainingSetError):
        fit_nearest_centroid([], CLASS_LABELS)


def test_fit_nearest_centroid_rejects_unexpected_label():
    cases = [_case("C", 60.0, 100.0, 100.0, 100.0)]
    with pytest.raises(MissingClassError):
        fit_nearest_centroid(cases, CLASS_LABELS)


def test_fit_nearest_centroid_rejects_missing_class():
    cases = [_case("A", 60.0, 100.0, 100.0, 100.0)]
    with pytest.raises(MissingClassError):
        fit_nearest_centroid(cases, CLASS_LABELS)  # no "B" cases at all


def test_evaluate_rejects_empty_cases():
    with pytest.raises(EmptyTrainingSetError):
        evaluate({"A": dict.fromkeys(FEATURE_NAMES, 0.0), "B": dict.fromkeys(FEATURE_NAMES, 1.0)}, [])


def test_fit_then_evaluate_on_well_separated_synthetic_clusters():
    # Two well-separated clusters: fitting on one half and evaluating on the
    # other half (a real train/test split) should still recover them cleanly.
    train_cases = [
        _case("A", 65.0, 140.0, 140.0, 120.0),
        _case("A", 63.0, 138.0, 142.0, 118.0),
        _case("A", 67.0, 142.0, 138.0, 122.0),
        _case("B", 25.0, 260.0, 140.0, 150.0),
        _case("B", 23.0, 258.0, 142.0, 148.0),
        _case("B", 27.0, 262.0, 138.0, 152.0),
    ]
    test_cases = [
        _case("A", 64.0, 141.0, 139.0, 121.0),
        _case("B", 26.0, 259.0, 141.0, 149.0),
    ]

    prototypes = fit_nearest_centroid(train_cases, CLASS_LABELS)
    result = evaluate(prototypes, test_cases)

    assert result.accuracy == pytest.approx(1.0)
    assert result.case_count == 2
    assert result.correct_count == 2
    assert result.per_class_accuracy == {"A": pytest.approx(1.0), "B": pytest.approx(1.0)}


def test_fitted_prototypes_are_usable_directly_with_classify_with_prototypes():
    train_cases = [
        _case("A", 65.0, 140.0, 140.0, 120.0),
        _case("B", 25.0, 260.0, 140.0, 150.0),
    ]
    prototypes = fit_nearest_centroid(train_cases, CLASS_LABELS)

    result = classify_with_prototypes(
        {"EJECTION_FRACTION": 64.0, "LV_EDV": 139.0, "RV_EDV": 141.0, "LV_MASS": 119.0}, prototypes
    )
    assert result.predicted_class == "A"
