"""Assembles the full classification validation report (confusion matrices,
per-class/macro/weighted/micro metrics, ROC/PR, calibration, selective
prediction, bootstrap CIs) into one JSON-serializable dict, from nothing
more than already-computed predictions/targets/probabilities.

Deliberately takes no model, dataset, or file paths — a pure function of
arrays — so both `train_classification.py` (real GPU run) and a unit test
(synthetic arrays, no GPU) exercise the exact same code path.
"""
from collections.abc import Sequence

import numpy as np

from . import classification_metrics as cm
from .fold_stats import bootstrap_ci


def _roc_result_to_dict(result: cm.RocResult) -> dict:
    return {"fpr": result.fpr.tolist(), "tpr": result.tpr.tolist(), "auc": result.auc}


def _pr_result_to_dict(result: cm.PrResult) -> dict:
    return {
        "precision": result.precision.tolist(),
        "recall": result.recall.tolist(),
        "average_precision": result.average_precision,
    }


def _reliability_to_dict(diagram: cm.ReliabilityDiagram) -> dict:
    return {
        "bin_confidence": diagram.bin_confidence.tolist(),
        "bin_accuracy": diagram.bin_accuracy.tolist(),
        "bin_count": diagram.bin_count.tolist(),
        "ece": diagram.ece,
        "mce": diagram.mce,
        "calibration_slope": diagram.calibration_slope,
        "calibration_intercept": diagram.calibration_intercept,
    }


def run_full_classification_validation(
    predictions: Sequence[str],
    targets: Sequence[str],
    probabilities: np.ndarray,
    labels: Sequence[str],
    *,
    n_bootstrap: int = 2000,
    bootstrap_seed: int = 42,
) -> dict:
    """`probabilities` is (n_samples, len(labels)) in `labels` order,
    row-aligned with `predictions`/`targets`."""
    labels = list(labels)
    confusion = cm.confusion_matrix(predictions, targets, labels)
    per_class = cm.per_class_metrics(confusion)
    confidences = probabilities.max(axis=1)
    correct = [p == t for p, t in zip(predictions, targets, strict=True)]

    macro_p, macro_r, macro_f1 = cm.macro_precision_recall_f1(confusion)
    weighted_p, weighted_r, weighted_f1 = cm.weighted_precision_recall_f1(predictions, targets, labels)
    micro_p, micro_r, micro_f1 = cm.micro_precision_recall_f1(confusion)

    roc_per_class = cm.roc_one_vs_rest(probabilities, targets, labels)
    pr_per_class = cm.pr_curve_one_vs_rest(probabilities, targets, labels)
    micro_roc = cm.micro_average_roc(probabilities, targets, labels)
    top1_reliability = cm.top1_reliability_diagram(confidences, correct)

    def _bootstrap_metric(indices: np.ndarray, metric_fn) -> float:
        sampled_predictions = [predictions[i] for i in indices]
        sampled_targets = [targets[i] for i in indices]
        return metric_fn(sampled_predictions, sampled_targets)

    def _bootstrap_macro_f1(indices: np.ndarray) -> float:
        sampled_predictions = [predictions[i] for i in indices]
        sampled_targets = [targets[i] for i in indices]
        sampled_cm = cm.confusion_matrix(sampled_predictions, sampled_targets, labels)
        return cm.macro_precision_recall_f1(sampled_cm)[2]

    n = len(predictions)
    accuracy_ci = bootstrap_ci(n, lambda idx: _bootstrap_metric(idx, cm.accuracy), n_resamples=n_bootstrap, seed=bootstrap_seed)
    balanced_accuracy_ci = bootstrap_ci(
        n, lambda idx: _bootstrap_metric(idx, cm.balanced_accuracy), n_resamples=n_bootstrap, seed=bootstrap_seed
    )
    macro_f1_ci = bootstrap_ci(n, _bootstrap_macro_f1, n_resamples=n_bootstrap, seed=bootstrap_seed)

    predictions_list = list(predictions)
    targets_list = list(targets)
    risk_coverage = cm.risk_coverage_curve(predictions_list, targets_list, confidences.tolist(), labels)

    return {
        "labels": labels,
        "sample_count": n,
        "confusion_matrix": confusion.tolist(),
        "confusion_matrix_normalized_true": cm.confusion_matrix_normalized(confusion, by="true").tolist(),
        "confusion_matrix_normalized_predicted": cm.confusion_matrix_normalized(confusion, by="predicted").tolist(),
        "accuracy": cm.accuracy(predictions, targets),
        "balanced_accuracy": cm.balanced_accuracy(predictions, targets),
        "error_rate": cm.error_rate(predictions, targets),
        "per_class": {
            label: {
                "precision": float(per_class.precision[i]),
                "recall": float(per_class.recall[i]),
                "specificity": float(per_class.specificity[i]),
                "npv": float(per_class.npv[i]),
                "f1": float(per_class.f1[i]),
            }
            for i, label in enumerate(labels)
        },
        "macro": {"precision": macro_p, "recall": macro_r, "f1": macro_f1},
        "weighted": {"precision": weighted_p, "recall": weighted_r, "f1": weighted_f1},
        "micro": {"precision": micro_p, "recall": micro_r, "f1": micro_f1},
        "matthews_correlation_coefficient": cm.matthews_correlation_coefficient(predictions, targets),
        "cohens_kappa": cm.cohens_kappa(predictions, targets),
        "top_2_accuracy": cm.top_k_accuracy(probabilities, targets, labels, k=2) if len(labels) > 2 else None,
        "roc": {
            "per_class": {label: _roc_result_to_dict(result) for label, result in roc_per_class.items()},
            "macro_auc": cm.macro_auc(probabilities, targets, labels),
            "weighted_auc": cm.weighted_auc(probabilities, targets, labels),
            "micro": _roc_result_to_dict(micro_roc),
        },
        "precision_recall": {
            "per_class": {label: _pr_result_to_dict(result) for label, result in pr_per_class.items()},
            "macro_pr_auc": cm.macro_pr_auc(probabilities, targets, labels),
            "micro_pr_auc": cm.micro_pr_auc(probabilities, targets, labels),
            "weighted_pr_auc": cm.weighted_pr_auc(probabilities, targets, labels),
            "prevalence": {label: sum(1 for t in targets if t == label) / n for label in labels},
        },
        "calibration": {
            "multiclass_brier_score": cm.multiclass_brier_score(probabilities, targets, labels),
            "per_class_brier_score": cm.per_class_brier_score(probabilities, targets, labels),
            "log_loss": cm.multiclass_log_loss(probabilities, targets, labels),
            "top1_reliability_diagram": _reliability_to_dict(top1_reliability),
            "high_confidence_error_rate_90": cm.high_confidence_error_rate(confidences, correct, threshold=0.9),
        },
        "selective_prediction": {
            "risk_coverage_curve": [
                {"coverage": p.coverage, "accuracy": p.accuracy, "macro_f1": p.macro_f1} for p in risk_coverage
            ],
            "selective_accuracy_reject_5pct": cm.selective_accuracy_at_rejection(
                predictions_list, targets_list, confidences.tolist(), reject_fraction=0.05
            ),
            "selective_accuracy_reject_10pct": cm.selective_accuracy_at_rejection(
                predictions_list, targets_list, confidences.tolist(), reject_fraction=0.10
            ),
            "selective_accuracy_reject_20pct": cm.selective_accuracy_at_rejection(
                predictions_list, targets_list, confidences.tolist(), reject_fraction=0.20
            ),
        },
        "bootstrap_ci_95": {
            "accuracy": list(accuracy_ci),
            "balanced_accuracy": list(balanced_accuracy_ci),
            "macro_f1": list(macro_f1_ci),
        },
    }
