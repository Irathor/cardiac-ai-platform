"""Multiclass classification validation metrics for the diagnosis classifiers
(nearest-centroid and CNN3D alike — both produce a predicted label plus a
per-class probability distribution, which is all these functions need).

Thin wrappers over `sklearn.metrics` where it already does the job correctly
(confusion matrix, per-class ROC/PR, MCC, Cohen's Kappa) — reimplementing
those would just be a slower, less-tested copy. But NOT for multiclass
`roc_auc_score(multi_class=...)` or `log_loss`: both silently assume
`y_score`'s columns are already sorted to match `sorted(labels)`
lexicographically, no matter what order the `labels` argument is actually
passed in (a documented-in-passing sklearn quirk, easy to trip over —
verified empirically here, see the macro/weighted AUC and log-loss
functions below). This project's label order is `DiagnosisClass`'s
declaration order, not alphabetical, so macro AUC is instead built by
averaging the (unambiguous, per-class-binary) `roc_one_vs_rest` results,
and log loss is computed directly from its one-line definition. The
functions written from scratch here (per-class specificity/NPV,
calibration/ECE, risk-coverage) are also ones scikit-learn doesn't provide
directly.

Every function takes plain Python lists/arrays of already-computed
predictions/probabilities — no I/O, no torch — so it's usable from both the
CNN3D training script and (via the same predicted-vs-reference-biomarker
comparison) the nearest-centroid path.
"""
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    cohen_kappa_score,
    confusion_matrix as sk_confusion_matrix,
    matthews_corrcoef,
    precision_recall_curve,
    precision_recall_fscore_support,
    roc_auc_score,
    roc_curve,
)

Labels = Sequence[str]


def confusion_matrix(predictions: Sequence[str], targets: Sequence[str], labels: Labels) -> np.ndarray:
    return sk_confusion_matrix(targets, predictions, labels=list(labels))


def confusion_matrix_normalized(cm: np.ndarray, *, by: str) -> np.ndarray:
    """`by="true"` normalizes each row (how a real class's cases were
    predicted); `by="predicted"` normalizes each column (how trustworthy a
    given prediction is). Rows/columns that sum to zero (a class absent from
    this split) are left as zero rather than producing NaN."""
    if by not in ("true", "predicted"):
        raise ValueError('by must be "true" or "predicted"')
    axis = 1 if by == "true" else 0
    totals = cm.sum(axis=axis, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        normalized = np.divide(cm, totals, out=np.zeros_like(cm, dtype=float), where=totals != 0)
    return normalized


@dataclass(frozen=True)
class PerClassCounts:
    tp: np.ndarray
    fp: np.ndarray
    fn: np.ndarray
    tn: np.ndarray


def per_class_counts(cm: np.ndarray) -> PerClassCounts:
    """Derives TP/FP/FN/TN for every class from a single confusion matrix
    pass, instead of re-scanning the prediction list once per class (what a
    naive per-class loop over raw predictions would do)."""
    total = cm.sum()
    tp = np.diag(cm)
    fp = cm.sum(axis=0) - tp
    fn = cm.sum(axis=1) - tp
    tn = total - tp - fp - fn
    return PerClassCounts(tp=tp, fp=fp, fn=fn, tn=tn)


def _safe_divide(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    return np.divide(
        numerator, denominator, out=np.zeros_like(numerator, dtype=float), where=denominator != 0
    )


@dataclass(frozen=True)
class PerClassMetrics:
    precision: np.ndarray
    recall: np.ndarray  # a.k.a. sensitivity
    specificity: np.ndarray
    npv: np.ndarray
    f1: np.ndarray


def per_class_metrics(cm: np.ndarray) -> PerClassMetrics:
    counts = per_class_counts(cm)
    precision = _safe_divide(counts.tp, counts.tp + counts.fp)
    recall = _safe_divide(counts.tp, counts.tp + counts.fn)
    specificity = _safe_divide(counts.tn, counts.tn + counts.fp)
    npv = _safe_divide(counts.tn, counts.tn + counts.fn)
    f1 = _safe_divide(2 * precision * recall, precision + recall)
    return PerClassMetrics(precision=precision, recall=recall, specificity=specificity, npv=npv, f1=f1)


def accuracy(predictions: Sequence[str], targets: Sequence[str]) -> float:
    if not predictions:
        raise ValueError("cannot compute accuracy over zero predictions")
    return float(np.mean([p == t for p, t in zip(predictions, targets, strict=True)]))


def balanced_accuracy(predictions: Sequence[str], targets: Sequence[str]) -> float:
    return float(balanced_accuracy_score(targets, predictions))


def error_rate(predictions: Sequence[str], targets: Sequence[str]) -> float:
    return 1.0 - accuracy(predictions, targets)


def macro_precision_recall_f1(cm: np.ndarray) -> tuple[float, float, float]:
    metrics = per_class_metrics(cm)
    return float(np.mean(metrics.precision)), float(np.mean(metrics.recall)), float(np.mean(metrics.f1))


def weighted_precision_recall_f1(predictions: Sequence[str], targets: Sequence[str], labels: Labels) -> tuple[float, float, float]:
    precision, recall, f1, _ = precision_recall_fscore_support(
        targets, predictions, labels=list(labels), average="weighted", zero_division=0
    )
    return float(precision), float(recall), float(f1)


def micro_precision_recall_f1(cm: np.ndarray) -> tuple[float, float, float]:
    """Micro-averaging pools TP/FP/FN across all classes first — for a
    single-label multiclass problem this collapses to plain accuracy, but is
    reported separately since it's a distinct, commonly-requested metric."""
    counts = per_class_counts(cm)
    tp, fp, fn = counts.tp.sum(), counts.fp.sum(), counts.fn.sum()
    precision = float(_safe_divide(np.array([tp]), np.array([tp + fp]))[0])
    recall = float(_safe_divide(np.array([tp]), np.array([tp + fn]))[0])
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1


def matthews_correlation_coefficient(predictions: Sequence[str], targets: Sequence[str]) -> float:
    return float(matthews_corrcoef(targets, predictions))


def cohens_kappa(predictions: Sequence[str], targets: Sequence[str]) -> float:
    return float(cohen_kappa_score(targets, predictions))


def top_k_accuracy(probabilities: np.ndarray, targets: Sequence[str], labels: Labels, k: int = 2) -> float:
    """`probabilities` is (n_samples, n_classes) in `labels` order."""
    label_index = {label: i for i, label in enumerate(labels)}
    target_indices = np.array([label_index[t] for t in targets])
    top_k = np.argsort(-probabilities, axis=1)[:, :k]
    return float(np.mean([target_indices[i] in top_k[i] for i in range(len(targets))]))


# --- ROC / PR (one-vs-rest) --------------------------------------------------


@dataclass(frozen=True)
class RocResult:
    fpr: np.ndarray
    tpr: np.ndarray
    thresholds: np.ndarray
    auc: float


def roc_one_vs_rest(probabilities: np.ndarray, targets: Sequence[str], labels: Labels) -> dict[str, RocResult]:
    result: dict[str, RocResult] = {}
    for i, label in enumerate(labels):
        binary_targets = np.array([1 if t == label else 0 for t in targets])
        if binary_targets.sum() == 0 or binary_targets.sum() == len(binary_targets):
            continue  # AUC undefined with only one class present in this split
        fpr, tpr, thresholds = roc_curve(binary_targets, probabilities[:, i])
        auc = float(roc_auc_score(binary_targets, probabilities[:, i]))
        result[label] = RocResult(fpr=fpr, tpr=tpr, thresholds=thresholds, auc=auc)
    return result


def _auc_score(probabilities: np.ndarray, targets: Sequence[str], labels: Labels, *, weighted: bool) -> float | None:
    """Averages the per-class one-vs-rest AUCs from `roc_one_vs_rest` — which
    binarizes and scores one class at a time, so there's no column-ordering
    ambiguity — rather than calling `roc_auc_score(..., multi_class="ovr")`
    directly. That sklearn path silently assumes `y_score`'s columns are
    already sorted to match `sorted(labels)` lexicographically, regardless
    of what order `labels` is actually passed in; here `labels` is this
    project's DiagnosisClass enum order, not alphabetical, so trusting that
    sklearn assumption would silently score the wrong column against the
    wrong class.

    Averages only over classes with a defined one-vs-rest AUC — a class
    entirely absent from (or entirely filling) this split doesn't have one,
    but that shouldn't make the whole macro/weighted average undefined when
    other classes have plenty of real data. Returns None only when no class
    has a defined AUC at all."""
    per_class = roc_one_vs_rest(probabilities, targets, labels)
    if not per_class:
        return None
    if not weighted:
        return float(np.mean([r.auc for r in per_class.values()]))
    support = {label: sum(1 for t in targets if t == label) for label in per_class}
    total = sum(support.values())
    return float(sum(r.auc * support[label] / total for label, r in per_class.items()))


def macro_auc(probabilities: np.ndarray, targets: Sequence[str], labels: Labels) -> float | None:
    return _auc_score(probabilities, targets, labels, weighted=False)


def weighted_auc(probabilities: np.ndarray, targets: Sequence[str], labels: Labels) -> float | None:
    return _auc_score(probabilities, targets, labels, weighted=True)


def micro_average_roc(probabilities: np.ndarray, targets: Sequence[str], labels: Labels) -> RocResult:
    """Standard micro-average recipe (scikit-learn docs): one-hot-encode
    every class as its own binary problem, then pool (ravel) all of them
    into one FPR/TPR curve instead of averaging per-class curves directly."""
    label_index = {label: i for i, label in enumerate(labels)}
    one_hot = np.zeros((len(targets), len(labels)), dtype=int)
    for row, t in enumerate(targets):
        one_hot[row, label_index[t]] = 1
    fpr, tpr, thresholds = roc_curve(one_hot.ravel(), probabilities.ravel())
    auc = float(roc_auc_score(one_hot.ravel(), probabilities.ravel()))
    return RocResult(fpr=fpr, tpr=tpr, thresholds=thresholds, auc=auc)


@dataclass(frozen=True)
class PrResult:
    precision: np.ndarray
    recall: np.ndarray
    thresholds: np.ndarray
    average_precision: float


def pr_curve_one_vs_rest(probabilities: np.ndarray, targets: Sequence[str], labels: Labels) -> dict[str, PrResult]:
    result: dict[str, PrResult] = {}
    for i, label in enumerate(labels):
        binary_targets = np.array([1 if t == label else 0 for t in targets])
        if binary_targets.sum() == 0:
            continue  # average precision undefined with zero positives
        precision, recall, thresholds = precision_recall_curve(binary_targets, probabilities[:, i])
        ap = float(average_precision_score(binary_targets, probabilities[:, i]))
        result[label] = PrResult(precision=precision, recall=recall, thresholds=thresholds, average_precision=ap)
    return result


def macro_pr_auc(probabilities: np.ndarray, targets: Sequence[str], labels: Labels) -> float:
    per_class = pr_curve_one_vs_rest(probabilities, targets, labels)
    if not per_class:
        return 0.0
    return float(np.mean([r.average_precision for r in per_class.values()]))


def micro_pr_auc(probabilities: np.ndarray, targets: Sequence[str], labels: Labels) -> float:
    label_index = {label: i for i, label in enumerate(labels)}
    one_hot = np.zeros((len(targets), len(labels)), dtype=int)
    for row, t in enumerate(targets):
        one_hot[row, label_index[t]] = 1
    return float(average_precision_score(one_hot.ravel(), probabilities.ravel()))


def weighted_pr_auc(probabilities: np.ndarray, targets: Sequence[str], labels: Labels) -> float:
    per_class = pr_curve_one_vs_rest(probabilities, targets, labels)
    if not per_class:
        return 0.0
    support = {label: sum(1 for t in targets if t == label) for label in labels}
    total = sum(support.values())
    return float(sum(r.average_precision * support[label] / total for label, r in per_class.items()))


# --- Probability quality: Brier score, log loss, calibration ----------------


def multiclass_brier_score(probabilities: np.ndarray, targets: Sequence[str], labels: Labels) -> float:
    """Mean squared error between the predicted probability vector and the
    one-hot true label, averaged over samples (the standard multiclass
    generalization of the binary Brier score)."""
    label_index = {label: i for i, label in enumerate(labels)}
    one_hot = np.zeros_like(probabilities)
    for row, t in enumerate(targets):
        one_hot[row, label_index[t]] = 1.0
    return float(np.mean(np.sum((probabilities - one_hot) ** 2, axis=1)))


def per_class_brier_score(probabilities: np.ndarray, targets: Sequence[str], labels: Labels) -> dict[str, float]:
    result = {}
    for i, label in enumerate(labels):
        binary_targets = np.array([1.0 if t == label else 0.0 for t in targets])
        result[label] = float(np.mean((probabilities[:, i] - binary_targets) ** 2))
    return result


def multiclass_log_loss(probabilities: np.ndarray, targets: Sequence[str], labels: Labels, *, eps: float = 1e-15) -> float:
    """Mean of -log(p_true_class), i.e. cross-entropy — computed directly
    rather than via `sklearn.metrics.log_loss` (see the module docstring:
    that function silently mis-scores non-alphabetically-ordered labels).
    Clipped to `eps` for the same numerical-stability reason sklearn's own
    implementation does."""
    label_index = {label: i for i, label in enumerate(labels)}
    true_class_probabilities = np.array(
        [probabilities[row, label_index[t]] for row, t in enumerate(targets)]
    )
    clipped = np.clip(true_class_probabilities, eps, 1.0)
    return float(-np.mean(np.log(clipped)))


@dataclass(frozen=True)
class ReliabilityDiagram:
    bin_confidence: np.ndarray  # mean predicted confidence in each bin
    bin_accuracy: np.ndarray  # observed accuracy in each bin
    bin_count: np.ndarray  # number of samples in each bin
    ece: float
    mce: float
    calibration_slope: float
    calibration_intercept: float


def top1_reliability_diagram(
    confidences: Sequence[float], correct: Sequence[bool], *, n_bins: int = 10
) -> ReliabilityDiagram:
    """Standard top-1 calibration analysis (Guo et al. 2017): bin predictions
    by their own max-softmax confidence, compare each bin's mean confidence
    against its observed accuracy. ECE/MCE are the sample-weighted / worst-
    case gap between the two across bins. Calibration slope/intercept come
    from an ordinary least-squares fit of observed accuracy on mean
    confidence across the (non-empty) bins — a simple, standard way to
    summarize over/under-confidence as a single line, distinct from ECE."""
    confidences_arr = np.asarray(confidences, dtype=float)
    correct_arr = np.asarray(correct, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_confidence = np.zeros(n_bins)
    bin_accuracy = np.zeros(n_bins)
    bin_count = np.zeros(n_bins, dtype=int)

    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        in_bin = (confidences_arr > lo) & (confidences_arr <= hi) if i > 0 else (confidences_arr >= lo) & (confidences_arr <= hi)
        count = int(in_bin.sum())
        bin_count[i] = count
        if count > 0:
            bin_confidence[i] = confidences_arr[in_bin].mean()
            bin_accuracy[i] = correct_arr[in_bin].mean()

    total = bin_count.sum()
    non_empty = bin_count > 0
    ece = float(np.sum(bin_count[non_empty] * np.abs(bin_accuracy[non_empty] - bin_confidence[non_empty])) / total) if total else 0.0
    mce = float(np.max(np.abs(bin_accuracy[non_empty] - bin_confidence[non_empty]))) if non_empty.any() else 0.0

    if non_empty.sum() >= 2:
        slope, intercept = np.polyfit(bin_confidence[non_empty], bin_accuracy[non_empty], 1)
    else:
        slope, intercept = float("nan"), float("nan")

    return ReliabilityDiagram(
        bin_confidence=bin_confidence, bin_accuracy=bin_accuracy, bin_count=bin_count,
        ece=ece, mce=mce, calibration_slope=float(slope), calibration_intercept=float(intercept),
    )


def per_class_reliability_diagram(
    probabilities: np.ndarray, targets: Sequence[str], labels: Labels, *, n_bins: int = 10
) -> dict[str, ReliabilityDiagram]:
    """One-vs-rest reliability diagram per class: for class `c`, "confidence"
    is P(c) and "correct" is whether the true label actually was `c`."""
    result = {}
    for i, label in enumerate(labels):
        binary_correct = [t == label for t in targets]
        result[label] = top1_reliability_diagram(probabilities[:, i], binary_correct, n_bins=n_bins)
    return result


def high_confidence_error_rate(confidences: Sequence[float], correct: Sequence[bool], *, threshold: float = 0.9) -> float:
    confidences_arr = np.asarray(confidences, dtype=float)
    correct_arr = np.asarray(correct, dtype=bool)
    high_confidence = confidences_arr > threshold
    if not high_confidence.any():
        return 0.0
    return float(np.mean(~correct_arr[high_confidence]))


# --- Selective prediction: risk-coverage ------------------------------------


@dataclass(frozen=True)
class RiskCoveragePoint:
    coverage: float
    accuracy: float
    macro_f1: float


def risk_coverage_curve(
    predictions: Sequence[str], targets: Sequence[str], confidences: Sequence[float], labels: Labels,
    *, coverage_steps: Sequence[float] = tuple(np.round(np.arange(1.0, 0.0, -0.05), 2)),
) -> list[RiskCoveragePoint]:
    """At each coverage level, keep the most-confident `coverage` fraction of
    predictions and report accuracy/macro-F1 on that retained subset — the
    standard selective-prediction curve (Geifman & El-Yaniv 2017 "SelectiveNet"
    convention: 100% coverage keeps everything, lower coverage keeps only the
    predictions the model is most confident about)."""
    order = np.argsort(-np.asarray(confidences, dtype=float))
    n = len(predictions)
    points = []
    for coverage in coverage_steps:
        keep_n = max(1, int(round(n * coverage)))
        kept_idx = order[:keep_n]
        kept_predictions = [predictions[i] for i in kept_idx]
        kept_targets = [targets[i] for i in kept_idx]
        cm = confusion_matrix(kept_predictions, kept_targets, labels)
        _, _, macro_f1 = macro_precision_recall_f1(cm)
        points.append(
            RiskCoveragePoint(coverage=keep_n / n, accuracy=accuracy(kept_predictions, kept_targets), macro_f1=macro_f1)
        )
    return points


def selective_accuracy_at_rejection(
    predictions: Sequence[str], targets: Sequence[str], confidences: Sequence[float], *, reject_fraction: float
) -> float:
    order = np.argsort(-np.asarray(confidences, dtype=float))
    n = len(predictions)
    keep_n = max(1, int(round(n * (1 - reject_fraction))))
    kept_idx = order[:keep_n]
    return accuracy([predictions[i] for i in kept_idx], [targets[i] for i in kept_idx])

