import numpy as np

from cardiac_ai_ml.dl.classification_validation import run_full_classification_validation

LABELS = ["NORMAL", "DCM", "HCM", "MINF", "RV"]


def _synthetic_case(n_per_class: int = 8, seed: int = 0):
    rng = np.random.default_rng(seed)
    targets = []
    probabilities = []
    for i, label in enumerate(LABELS):
        targets.extend([label] * n_per_class)
        base = np.full((n_per_class, len(LABELS)), 0.05)
        base[:, i] = 0.8  # mostly-correct, well-separated synthetic probabilities
        noise = rng.normal(scale=0.02, size=base.shape)
        probabilities.append(base + noise)
    probabilities = np.clip(np.concatenate(probabilities, axis=0), 1e-6, None)
    probabilities = probabilities / probabilities.sum(axis=1, keepdims=True)
    predictions = [LABELS[i] for i in probabilities.argmax(axis=1)]
    return predictions, targets, probabilities


def test_report_is_well_formed_and_internally_consistent():
    predictions, targets, probabilities = _synthetic_case()
    report = run_full_classification_validation(predictions, targets, probabilities, LABELS, n_bootstrap=200)

    assert report["labels"] == LABELS
    assert report["sample_count"] == len(predictions)
    assert len(report["confusion_matrix"]) == len(LABELS)
    assert 0.0 <= report["accuracy"] <= 1.0
    assert report["accuracy"] > 0.8  # well-separated synthetic case should classify easily

    for label in LABELS:
        assert label in report["per_class"]
        assert 0.0 <= report["per_class"][label]["f1"] <= 1.0

    assert set(report["macro"]) == {"precision", "recall", "f1"}
    assert report["roc"]["macro_auc"] is not None
    assert report["roc"]["macro_auc"] > 0.8
    assert report["precision_recall"]["macro_pr_auc"] > 0.8

    ci_low, ci_high = report["bootstrap_ci_95"]["accuracy"]
    assert ci_low <= report["accuracy"] <= ci_high

    assert len(report["selective_prediction"]["risk_coverage_curve"]) > 0
    assert 0.0 <= report["calibration"]["multiclass_brier_score"]


def test_report_handles_a_class_missing_entirely_from_the_split():
    n = 6
    targets = ["NORMAL"] * n
    probabilities = np.tile(np.array([0.6, 0.1, 0.1, 0.1, 0.1]), (n, 1))
    predictions = ["NORMAL"] * n
    report = run_full_classification_validation(predictions, targets, probabilities, LABELS, n_bootstrap=50)
    assert report["accuracy"] == 1.0
    # AUC for classes absent from targets is undefined -> reported as None, not fabricated.
    assert report["roc"]["per_class"].get("DCM") is None
