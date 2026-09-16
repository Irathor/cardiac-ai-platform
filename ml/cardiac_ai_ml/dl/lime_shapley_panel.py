"""Pedagogical LIME-vs-Shapley comparison panel over the nearest-centroid
biomarker classifier (`cardiac_ai_ml.classification`) — see ADR-3.

LIME (`lime.lime_tabular.LimeTabularExplainer`) is computed for real here
(sampling + a local linear surrogate, genuinely run — never simulated), but
strictly as a side-by-side comparison against the exact Shapley attribution
`cardiac_ai_ml.classification.explain_with_prototypes` already provides in
production. Every result this module returns is labelled with which method
produced it (`METHOD_LIME` vs `METHOD_SHAPLEY`) so it can never be confused
with the single production explanation mechanism (Shapley).

Lives under `cardiac_ai_ml.dl` (not the lightweight root package) purely
for dependency-gating consistency: `lime` ships only in the `dl` extra
alongside torch/monai, so anywhere that already skips `dl/*` when those
aren't installed (see `ml/tests/conftest.py`) also correctly skips this,
even though this module itself never imports torch.
"""
from dataclasses import dataclass, field

import numpy as np
from lime.lime_tabular import LimeTabularExplainer

from ..classification import FEATURE_NAMES, Prototypes, classify_with_prototypes, explain_with_prototypes
from .acdc_dataset import AcdcPatient
from .predicted_biomarker_pipeline import reference_biomarker_features

METHOD_LIME = "LIME (aproximado)"
METHOD_SHAPLEY = "Shapley (exacto)"

PEDAGOGICAL_NOTE = (
    "Panel comparativo pedagogico (ver ADR-3): LIME es una aproximacion local "
    "por muestreo, nunca la explicacion de produccion. Shapley exacto sigue "
    "siendo el unico mecanismo de explicabilidad servido en produccion."
)


def real_background_biomarker_features(patients: list[AcdcPatient], limit: int | None = None) -> list[dict[str, float]]:
    """Real biomarkers computed from real ACDC ground-truth masks (reusing
    `predicted_biomarker_pipeline.reference_biomarker_features`) — used as
    LIME's background/perturbation distribution instead of a fabricated
    one, so its local sampling reflects the actual biomarker distribution
    this classifier operates over."""
    selected = patients if limit is None else patients[:limit]
    return [reference_biomarker_features(p) for p in selected]


def build_lime_explainer(background_features: list[dict[str, float]], class_names: list[str], *, seed: int = 42) -> LimeTabularExplainer:
    if not background_features:
        raise ValueError("background_features must not be empty")
    training_data = np.array([[row[name] for name in FEATURE_NAMES] for row in background_features])
    return LimeTabularExplainer(
        training_data,
        feature_names=list(FEATURE_NAMES),
        class_names=list(class_names),
        mode="classification",
        discretize_continuous=False,
        random_state=seed,
    )


def _predict_proba_fn(prototypes: Prototypes, class_names: list[str]):
    def predict_proba(feature_matrix: np.ndarray) -> np.ndarray:
        rows = []
        for values in feature_matrix:
            features = dict(zip(FEATURE_NAMES, values, strict=True))
            result = classify_with_prototypes(features, prototypes)
            rows.append([result.probabilities.get(label, 0.0) for label in class_names])
        return np.array(rows)

    return predict_proba


def lime_attribution(
    explainer: LimeTabularExplainer,
    features: dict[str, float],
    prototypes: Prototypes,
    class_names: list[str],
    *,
    num_samples: int = 2000,
) -> dict[str, float]:
    """Real LIME attribution (genuinely sampled + fit, not simulated) for
    the classifier's own predicted class."""
    predict_proba = _predict_proba_fn(prototypes, class_names)
    row = np.array([features[name] for name in FEATURE_NAMES])
    predicted_class = classify_with_prototypes(features, prototypes).predicted_class
    label_index = class_names.index(predicted_class)

    explanation = explainer.explain_instance(
        row, predict_proba, labels=(label_index,), num_features=len(FEATURE_NAMES), num_samples=num_samples
    )
    # discretize_continuous=False -> LIME's feature "description" is exactly
    # the feature name (no binning/thresholding text to parse out).
    raw = dict(explanation.as_list(label=label_index))
    return {name: raw.get(name, 0.0) for name in FEATURE_NAMES}


@dataclass(frozen=True)
class ExplanationPanel:
    patient_id: str
    predicted_class: str
    method_attributions: dict[str, dict[str, float]]  # {METHOD_LIME: {...}, METHOD_SHAPLEY: {...}}
    note: str = field(default=PEDAGOGICAL_NOTE)


def build_explanation_panel(
    patient_id: str,
    features: dict[str, float],
    prototypes: Prototypes,
    baseline: dict[str, float],
    explainer: LimeTabularExplainer,
    class_names: list[str],
    *,
    num_samples: int = 2000,
) -> ExplanationPanel:
    predicted_class = classify_with_prototypes(features, prototypes).predicted_class
    shapley = explain_with_prototypes(features, prototypes, baseline)
    lime = lime_attribution(explainer, features, prototypes, class_names, num_samples=num_samples)
    return ExplanationPanel(
        patient_id=patient_id,
        predicted_class=predicted_class,
        method_attributions={METHOD_LIME: lime, METHOD_SHAPLEY: shapley},
    )
