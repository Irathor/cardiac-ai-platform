"""Nearest-prototype disease classifier and explainability.

Two ways to get prototypes:

- `classify_demo`/`explain_demo` use five illustrative, hand-picked biomarker
  profiles loosely inspired by the ACDC challenge's diagnostic categories —
  NOT derived from real training data and NOT clinically validated. This is
  what runs before any real model has been trained (see
  docs/clinical-limitations.md).
- `cardiac_ai_ml.training.fit_nearest_centroid` computes real prototypes —
  the per-class mean feature vector — from a dataset's TRAIN split. Both
  paths converge on the same `classify_with_prototypes`/`explain_with_prototypes`
  functions below, so a trained model and the demo heuristic are
  interchangeable from every caller's point of view (see
  app.services.analysis_service, which picks whichever is active).

Explainability uses exact Shapley values (game-theoretic feature
attribution), which is model-agnostic and works correctly on any function —
including a simple nearest-prototype rule — so, unlike Grad-CAM (which needs
a real CNN's activation maps and therefore cannot exist until a real image
model is trained), this part is genuine, not a placeholder.
"""
import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from itertools import combinations

FEATURE_NAMES = ("EJECTION_FRACTION", "LV_EDV", "RV_EDV", "LV_MASS")


class DiagnosisClass(str, Enum):
    NORMAL = "NORMAL"
    DILATED_CARDIOMYOPATHY = "DILATED_CARDIOMYOPATHY"
    HYPERTROPHIC_CARDIOMYOPATHY = "HYPERTROPHIC_CARDIOMYOPATHY"
    MYOCARDIAL_INFARCTION = "MYOCARDIAL_INFARCTION"
    ABNORMAL_RIGHT_VENTRICLE = "ABNORMAL_RIGHT_VENTRICLE"


Prototypes = dict[str, dict[str, float]]  # {class_value: {feature_name: value}}

# (ejection_fraction_percent, lv_edv_ml, rv_edv_ml, lv_mass_g) — illustrative
# centroids only, not fitted to real data.
_DEMO_PROTOTYPES: Prototypes = {
    DiagnosisClass.NORMAL.value: dict(zip(FEATURE_NAMES, (65.0, 140.0, 140.0, 120.0), strict=True)),
    DiagnosisClass.DILATED_CARDIOMYOPATHY.value: dict(zip(FEATURE_NAMES, (25.0, 260.0, 140.0, 150.0), strict=True)),
    DiagnosisClass.HYPERTROPHIC_CARDIOMYOPATHY.value: dict(zip(FEATURE_NAMES, (65.0, 110.0, 110.0, 200.0), strict=True)),
    DiagnosisClass.MYOCARDIAL_INFARCTION.value: dict(zip(FEATURE_NAMES, (35.0, 160.0, 140.0, 120.0), strict=True)),
    DiagnosisClass.ABNORMAL_RIGHT_VENTRICLE.value: dict(zip(FEATURE_NAMES, (60.0, 140.0, 220.0, 110.0), strict=True)),
}

# Rough typical spread per feature, used to make distances comparable across
# features with very different units/scales. Kept fixed (not fitted) even
# for a trained model — it's a normalization constant, not a parameter.
FEATURE_SCALES: dict[str, float] = {
    "EJECTION_FRACTION": 15.0,
    "LV_EDV": 50.0,
    "RV_EDV": 50.0,
    "LV_MASS": 40.0,
}

_DEMO_BASELINE = _DEMO_PROTOTYPES[DiagnosisClass.NORMAL.value]


@dataclass(frozen=True)
class ClassificationResult:
    # A plain str (not DiagnosisClass) so classify_with_prototypes stays usable
    # with any label set, not just the demo/production 5-class taxonomy (see
    # ml/tests/test_training.py, which fits/evaluates over a toy 2-class set).
    # Str Enum members still compare equal to the plain string with the same
    # value, so `result.predicted_class == DiagnosisClass.NORMAL` still works.
    predicted_class: str
    probabilities: dict[str, float]

    @property
    def confidence(self) -> float:
        return self.probabilities[self.predicted_class]


def _class_score(prototype: dict[str, float], features: dict[str, float]) -> float:
    """Negative squared distance to a class prototype, in scale-normalized
    units. Higher (closer to zero) means more consistent with this class."""
    total = 0.0
    for name in FEATURE_NAMES:
        scaled_diff = (features[name] - prototype[name]) / FEATURE_SCALES[name]
        total += scaled_diff**2
    return -total


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    max_score = max(scores.values())
    exp_scores = {k: math.exp(v - max_score) for k, v in scores.items()}
    total = sum(exp_scores.values())
    return {k: v / total for k, v in exp_scores.items()}


def classify_with_prototypes(features: dict[str, float], prototypes: Prototypes) -> ClassificationResult:
    """`features` must have exactly the keys in FEATURE_NAMES. `prototypes`
    just needs at least one class — it is not required to cover every
    DiagnosisClass value, so this stays usable for a partial/toy label set
    too (see ml/tests/test_training.py); the caller decides what "complete"
    means (classify_demo uses all 5, fit_nearest_centroid enforces its own
    `class_labels` are all present when called from the training pipeline)."""
    missing = set(FEATURE_NAMES) - features.keys()
    if missing:
        raise ValueError(f"missing required feature(s): {sorted(missing)}")
    if not prototypes:
        raise ValueError("prototypes must not be empty")

    scores = {label: _class_score(prototype, features) for label, prototype in prototypes.items()}
    probabilities = _softmax(scores)
    predicted_label = max(probabilities, key=probabilities.get)
    return ClassificationResult(predicted_class=predicted_label, probabilities=probabilities)


def classify_demo(features: dict[str, float]) -> ClassificationResult:
    return classify_with_prototypes(features, _DEMO_PROTOTYPES)


def shapley_values(
    value_fn: Callable[[frozenset[str]], float], feature_names: tuple[str, ...]
) -> dict[str, float]:
    """Exact Shapley values of `value_fn` over `feature_names`.

    `value_fn(S)` must return the coalition value for a subset `S` of feature
    names (i.e. "what would the model output if only the features in S were
    known, with everything else at some fixed baseline"). Exponential in the
    number of features, which is fine for the handful of biomarkers here.
    """
    n = len(feature_names)
    others_by_feature = {name: [f for f in feature_names if f != name] for name in feature_names}
    phi: dict[str, float] = {}

    for name in feature_names:
        others = others_by_feature[name]
        total = 0.0
        for r in range(len(others) + 1):
            for subset in combinations(others, r):
                s = frozenset(subset)
                weight = math.factorial(len(s)) * math.factorial(n - len(s) - 1) / math.factorial(n)
                total += weight * (value_fn(s | {name}) - value_fn(s))
        phi[name] = total
    return phi


def explain_with_prototypes(
    features: dict[str, float], prototypes: Prototypes, baseline: dict[str, float]
) -> dict[str, float]:
    """Shapley attribution of each feature's contribution to the predicted
    class's score, relative to `baseline` (i.e. "how much does each
    biomarker push the result away from a normal-looking heart")."""
    result = classify_with_prototypes(features, prototypes)
    predicted_prototype = prototypes[result.predicted_class]

    def value_fn(known: frozenset[str]) -> float:
        effective = {name: (features[name] if name in known else baseline[name]) for name in FEATURE_NAMES}
        return _class_score(predicted_prototype, effective)

    return shapley_values(value_fn, FEATURE_NAMES)


def explain_demo(features: dict[str, float]) -> dict[str, float]:
    return explain_with_prototypes(features, _DEMO_PROTOTYPES, _DEMO_BASELINE)
