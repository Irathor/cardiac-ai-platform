"""Real (non-simulated) tests for the pedagogical LIME-vs-Shapley panel
(see ADR-3): LIME is genuinely sampled/fit here via `lime.lime_tabular`,
never faked, but always compared against — never substituted for — the
exact Shapley attribution already used in production.
"""
from cardiac_ai_ml.classification import DiagnosisClass, explain_with_prototypes
from cardiac_ai_ml.dl.lime_shapley_panel import (
    METHOD_LIME,
    METHOD_SHAPLEY,
    build_explanation_panel,
    build_lime_explainer,
)

CLASS_NAMES = [d.value for d in DiagnosisClass]

# A tiny, clearly-separated synthetic prototype set (real numbers, not
# drawn from real patients here — the point of these tests is to check the
# LIME/Shapley *mechanism* and its labelling, independent of real-data
# availability; `run_explainability_showcase.py` covers the real-ACDC-data
# path end to end).
PROTOTYPES = {
    DiagnosisClass.NORMAL.value: {"EJECTION_FRACTION": 65.0, "LV_EDV": 140.0, "RV_EDV": 140.0, "LV_MASS": 120.0},
    DiagnosisClass.DILATED_CARDIOMYOPATHY.value: {"EJECTION_FRACTION": 25.0, "LV_EDV": 260.0, "RV_EDV": 140.0, "LV_MASS": 150.0},
    DiagnosisClass.HYPERTROPHIC_CARDIOMYOPATHY.value: {"EJECTION_FRACTION": 65.0, "LV_EDV": 110.0, "RV_EDV": 110.0, "LV_MASS": 200.0},
    DiagnosisClass.MYOCARDIAL_INFARCTION.value: {"EJECTION_FRACTION": 35.0, "LV_EDV": 160.0, "RV_EDV": 140.0, "LV_MASS": 120.0},
    DiagnosisClass.ABNORMAL_RIGHT_VENTRICLE.value: {"EJECTION_FRACTION": 60.0, "LV_EDV": 140.0, "RV_EDV": 220.0, "LV_MASS": 110.0},
}
BASELINE = PROTOTYPES[DiagnosisClass.NORMAL.value]


def _synthetic_background(n_per_class: int = 20) -> list[dict[str, float]]:
    """A real (if synthetic) background distribution: small Gaussian jitter
    around each prototype, so LIME's local sampling has a sensible
    neighborhood to draw from — not literally patient data, but not a
    degenerate single-point background either."""
    import random

    rng = random.Random(42)
    background = []
    for prototype in PROTOTYPES.values():
        for _ in range(n_per_class):
            background.append({name: value + rng.uniform(-2.0, 2.0) for name, value in prototype.items()})
    return background


def test_lime_and_shapley_agree_in_sign_near_a_prototype() -> None:
    """For a case placed close to the DCM prototype (an easy, unambiguous
    case for both methods), ejection fraction — which differs by 40 points
    between NORMAL and DCM, far more than any other feature — should be
    identified by both methods as supporting the DCM prediction.

    These two methods report genuinely different quantities, not
    literally the same number with different noise (this is itself the
    pedagogical point of ADR-3's panel): Shapley here is a *value*
    attribution (how much does EF being 24, instead of the NORMAL baseline
    of 65, support DCM — a positive number), while raw LIME coefficients
    are *local slopes* (d(P(DCM))/d(EF) in a neighborhood of the query
    point) — since DCM's own case value (24) sits below the NORMAL
    baseline (65) on a feature where lower is more DCM-like, the slope is
    negative (probability drops as EF rises locally) even though the
    feature's actual value supports DCM. To compare like with like, LIME's
    slope is converted into the same "value attribution" quantity Shapley
    reports via a first-order Taylor step around the same NORMAL baseline
    Shapley uses (`slope * (value - baseline_value)`) — a standard way to
    turn a local linear-surrogate slope into a value attribution. Once
    both are expressed as value attributions, they agree in sign."""
    background = _synthetic_background()
    explainer = build_lime_explainer(background, CLASS_NAMES)

    near_dcm_case = {"EJECTION_FRACTION": 24.0, "LV_EDV": 258.0, "RV_EDV": 141.0, "LV_MASS": 149.0}
    panel = build_explanation_panel(
        "synthetic-near-dcm", near_dcm_case, PROTOTYPES, BASELINE, explainer, CLASS_NAMES, num_samples=4000
    )

    assert panel.predicted_class == DiagnosisClass.DILATED_CARDIOMYOPATHY.value
    lime_slope = panel.method_attributions[METHOD_LIME]["EJECTION_FRACTION"]
    shapley_value_attribution = panel.method_attributions[METHOD_SHAPLEY]["EJECTION_FRACTION"]
    lime_value_attribution = lime_slope * (near_dcm_case["EJECTION_FRACTION"] - BASELINE["EJECTION_FRACTION"])

    assert shapley_value_attribution > 0
    assert lime_value_attribution > 0


def test_lime_and_shapley_are_labelled_and_never_mixed() -> None:
    """Coherent with ADR-3: the panel must always keep LIME and Shapley
    results under distinct, explicit labels — never merged into a single
    unlabelled attribution dict that a caller could mistake for one
    method's output."""
    background = _synthetic_background()
    explainer = build_lime_explainer(background, CLASS_NAMES)

    case = {"EJECTION_FRACTION": 64.0, "LV_EDV": 141.0, "RV_EDV": 139.0, "LV_MASS": 121.0}
    panel = build_explanation_panel("synthetic-near-normal", case, PROTOTYPES, BASELINE, explainer, CLASS_NAMES)

    assert set(panel.method_attributions) == {METHOD_LIME, METHOD_SHAPLEY}
    assert METHOD_LIME != METHOD_SHAPLEY
    assert "aproximado" in METHOD_LIME.lower()
    assert "exacto" in METHOD_SHAPLEY.lower()
    assert "ADR-3" in panel.note or "ADR-3".lower() in panel.note.lower() or "pedagog" in panel.note.lower()

    # Both methods must report every biomarker feature, never a partial set
    # that could be misread as "the feature had no effect".
    from cardiac_ai_ml.classification import FEATURE_NAMES

    assert set(panel.method_attributions[METHOD_LIME]) == set(FEATURE_NAMES)
    assert set(panel.method_attributions[METHOD_SHAPLEY]) == set(FEATURE_NAMES)


def test_shapley_reference_matches_classification_module_directly() -> None:
    """The panel's Shapley numbers must be identical to calling
    `cardiac_ai_ml.classification.explain_with_prototypes` directly — the
    panel must never compute its own separate/approximate version of the
    "exact" side."""
    background = _synthetic_background()
    explainer = build_lime_explainer(background, CLASS_NAMES)
    case = {"EJECTION_FRACTION": 64.0, "LV_EDV": 141.0, "RV_EDV": 139.0, "LV_MASS": 121.0}

    panel = build_explanation_panel("synthetic-near-normal", case, PROTOTYPES, BASELINE, explainer, CLASS_NAMES)
    direct_shapley = explain_with_prototypes(case, PROTOTYPES, BASELINE)

    assert panel.method_attributions[METHOD_SHAPLEY] == direct_shapley
