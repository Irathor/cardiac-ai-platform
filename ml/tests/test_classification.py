import pytest

from cardiac_ai_ml.classification import (
    FEATURE_NAMES,
    DiagnosisClass,
    Prototypes,
    _class_score,
    biomarker_consistency,
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


# --- biomarker_consistency ---------------------------------------------

_TEST_PROTOTYPE = {"EJECTION_FRACTION": 60.0, "LV_EDV": 140.0, "RV_EDV": 140.0, "LV_MASS": 120.0}
_OTHER_PROTOTYPE = {"EJECTION_FRACTION": 20.0, "LV_EDV": 260.0, "RV_EDV": 140.0, "LV_MASS": 150.0}
_TEST_PROTOTYPES: Prototypes = {"TESTCLASS": _TEST_PROTOTYPE, "OTHERCLASS": _OTHER_PROTOTYPE}


def test_biomarker_consistency_flags_close_biomarkers_as_consistent():
    # Every feature is half a FEATURE_SCALES unit away from the prototype
    # (sign alternated to also exercise the negative-deviation path), so by
    # hand: scaled_deviation is exactly +/-0.5 for all four features, well
    # inside the |.| <= 1.0 consistency threshold.
    features = {
        "EJECTION_FRACTION": 60.0 + 0.5 * 15.0,  # 67.5 -> +0.5
        "LV_EDV": 140.0 + 0.5 * 50.0,  # 165.0 -> +0.5
        "RV_EDV": 140.0 - 0.5 * 50.0,  # 115.0 -> -0.5
        "LV_MASS": 120.0 + 0.5 * 40.0,  # 140.0 -> +0.5
    }

    result = biomarker_consistency(features, _TEST_PROTOTYPES, "TESTCLASS", reference_source="demo-heuristic-v1")

    assert result.predicted_class == "TESTCLASS"
    assert result.reference_source == "demo-heuristic-v1"

    expected_signed_deviation = {
        "EJECTION_FRACTION": 0.5,
        "LV_EDV": 0.5,
        "RV_EDV": -0.5,
        "LV_MASS": 0.5,
    }
    by_feature = {fc.feature: fc for fc in result.per_feature}
    assert set(by_feature) == set(FEATURE_NAMES)
    for name in FEATURE_NAMES:
        fc = by_feature[name]
        assert fc.derived_value == pytest.approx(features[name])
        assert fc.expected_value_for_predicted_class == pytest.approx(_TEST_PROTOTYPE[name])
        assert fc.scaled_deviation == pytest.approx(expected_signed_deviation[name])
        assert fc.consistent is True

    # sqrt(0.5^2 * 4) == sqrt(1.0) == 1.0, by hand.
    assert result.distance_to_each_class["TESTCLASS"] == pytest.approx(1.0)
    assert set(result.distance_to_each_class) == {"TESTCLASS", "OTHERCLASS"}


def test_biomarker_consistency_flags_diverging_biomarker_as_inconsistent():
    # Only LV_MASS moves, by two full FEATURE_SCALES units (80 g, scale 40):
    # scaled_deviation == 2.0, outside the |.| <= 1.0 threshold, so that
    # feature alone must be flagged inconsistent while the rest (unchanged,
    # scaled_deviation == 0.0) stay consistent.
    features = {**_TEST_PROTOTYPE, "LV_MASS": 200.0}

    result = biomarker_consistency(features, _TEST_PROTOTYPES, "TESTCLASS", reference_source="demo-heuristic-v1")

    by_feature = {fc.feature: fc for fc in result.per_feature}
    assert by_feature["LV_MASS"].scaled_deviation == pytest.approx(2.0)
    assert by_feature["LV_MASS"].consistent is False
    for name in ("EJECTION_FRACTION", "LV_EDV", "RV_EDV"):
        assert by_feature[name].scaled_deviation == pytest.approx(0.0)
        assert by_feature[name].consistent is True

    # sqrt(2.0^2) == 2.0, by hand.
    assert result.distance_to_each_class["TESTCLASS"] == pytest.approx(2.0)

    as_dict = result.as_dict()
    assert as_dict["predicted_class"] == "TESTCLASS"
    assert as_dict["per_feature"][0]["feature"] == FEATURE_NAMES[0]
    assert any(not row["consistent"] for row in as_dict["per_feature"])


def test_biomarker_consistency_rejects_missing_features():
    with pytest.raises(ValueError):
        biomarker_consistency({"EJECTION_FRACTION": 60.0}, _TEST_PROTOTYPES, "TESTCLASS", reference_source="x")


def test_biomarker_consistency_rejects_unknown_predicted_class():
    with pytest.raises(ValueError):
        biomarker_consistency(_TEST_PROTOTYPE, _TEST_PROTOTYPES, "NOT_A_CLASS", reference_source="x")
