import pytest

from cardiac_ai_ml.classification import (
    FEATURE_NAMES,
    DiagnosisClass,
    _class_score,
    classify_demo,
    explain_demo,
    shapley_values,
)

NORMAL_FEATURES = {"EJECTION_FRACTION": 65.0, "LV_EDV": 140.0, "RV_EDV": 140.0, "LV_MASS": 120.0}


def test_classify_demo_recognizes_each_prototype_exactly():
    # Feeding a class's own prototype back in must classify as that class —
    # the whole point of a nearest-prototype rule.
    from cardiac_ai_ml.classification import _DEMO_PROTOTYPES

    for label, features in _DEMO_PROTOTYPES.items():
        result = classify_demo(features)
        assert result.predicted_class == DiagnosisClass(label)


def test_probabilities_sum_to_one_and_include_every_class():
    result = classify_demo(NORMAL_FEATURES)
    assert set(result.probabilities) == {d.value for d in DiagnosisClass}
    assert sum(result.probabilities.values()) == pytest.approx(1.0)


def test_confidence_is_the_predicted_classs_own_probability():
    result = classify_demo(NORMAL_FEATURES)
    assert result.confidence == result.probabilities[result.predicted_class]
    assert result.confidence == max(result.probabilities.values())


def test_exact_prototype_match_is_highly_confident():
    result = classify_demo(NORMAL_FEATURES)
    assert result.predicted_class == DiagnosisClass.NORMAL
    assert result.confidence > 0.9


def test_classify_demo_rejects_missing_features():
    with pytest.raises(ValueError):
        classify_demo({"EJECTION_FRACTION": 60.0})


def test_dilated_cardiomyopathy_profile_low_ef_high_lv_volume():
    features = {"EJECTION_FRACTION": 22.0, "LV_EDV": 270.0, "RV_EDV": 140.0, "LV_MASS": 150.0}
    assert classify_demo(features).predicted_class == DiagnosisClass.DILATED_CARDIOMYOPATHY


def test_hypertrophic_cardiomyopathy_profile_normal_ef_high_mass():
    features = {"EJECTION_FRACTION": 65.0, "LV_EDV": 105.0, "RV_EDV": 105.0, "LV_MASS": 210.0}
    assert classify_demo(features).predicted_class == DiagnosisClass.HYPERTROPHIC_CARDIOMYOPATHY


def test_abnormal_right_ventricle_profile_enlarged_rv():
    features = {"EJECTION_FRACTION": 60.0, "LV_EDV": 140.0, "RV_EDV": 230.0, "LV_MASS": 110.0}
    assert classify_demo(features).predicted_class == DiagnosisClass.ABNORMAL_RIGHT_VENTRICLE


def test_shapley_values_satisfy_the_efficiency_axiom():
    # The defining property of Shapley values: they exactly redistribute the
    # total gap between the full coalition's value and the empty coalition's
    # value ("efficiency" / local accuracy, same idea SHAP is built on).
    def value_fn(subset):
        known = {name: (10.0 if name in subset else 0.0) for name in FEATURE_NAMES}
        return sum(known.values())

    phi = shapley_values(value_fn, FEATURE_NAMES)
    full_value = value_fn(frozenset(FEATURE_NAMES))
    empty_value = value_fn(frozenset())
    assert sum(phi.values()) == pytest.approx(full_value - empty_value)


def test_shapley_values_are_symmetric_for_interchangeable_features():
    # A value function that treats two features identically must attribute
    # them equal Shapley value.
    def value_fn(subset):
        return float(len(subset & {"EJECTION_FRACTION", "LV_EDV"}))

    phi = shapley_values(value_fn, FEATURE_NAMES)
    assert phi["EJECTION_FRACTION"] == pytest.approx(phi["LV_EDV"])
    assert phi["RV_EDV"] == pytest.approx(0.0)
    assert phi["LV_MASS"] == pytest.approx(0.0)


def test_explain_demo_returns_all_features_and_respects_efficiency():
    features = {"EJECTION_FRACTION": 22.0, "LV_EDV": 270.0, "RV_EDV": 140.0, "LV_MASS": 150.0}
    attributions = explain_demo(features)

    assert set(attributions) == set(FEATURE_NAMES)

    from cardiac_ai_ml.classification import _DEMO_PROTOTYPES

    predicted = classify_demo(features).predicted_class
    prototype = _DEMO_PROTOTYPES[predicted]
    full_score = _class_score(prototype, features)
    baseline_score = _class_score(prototype, NORMAL_FEATURES)
    assert sum(attributions.values()) == pytest.approx(full_score - baseline_score)


def test_explain_demo_gives_near_zero_attribution_to_at_baseline_features():
    # A feature already at the NORMAL baseline shouldn't be blamed for the
    # abnormal prediction driven by the other features.
    features = {**NORMAL_FEATURES, "LV_MASS": 210.0}
    attributions = explain_demo(features)
    assert attributions["EJECTION_FRACTION"] == pytest.approx(0.0, abs=1e-9)
    assert attributions["LV_EDV"] == pytest.approx(0.0, abs=1e-9)
    assert attributions["RV_EDV"] == pytest.approx(0.0, abs=1e-9)
    assert abs(attributions["LV_MASS"]) > 0
