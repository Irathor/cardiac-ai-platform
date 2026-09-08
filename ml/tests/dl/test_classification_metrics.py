import numpy as np
import pytest

from cardiac_ai_ml.dl.classification_metrics import (
    accuracy,
    balanced_accuracy,
    cohens_kappa,
    confusion_matrix,
    confusion_matrix_normalized,
    error_rate,
    high_confidence_error_rate,
    macro_auc,
    macro_precision_recall_f1,
    matthews_correlation_coefficient,
    micro_average_roc,
    micro_pr_auc,
    micro_precision_recall_f1,
    multiclass_brier_score,
    multiclass_log_loss,
    per_class_metrics,
    pr_curve_one_vs_rest,
    risk_coverage_curve,
    roc_one_vs_rest,
    selective_accuracy_at_rejection,
    top1_reliability_diagram,
    top_k_accuracy,
    weighted_precision_recall_f1,
)

LABELS = ["A", "B", "C"]


def test_accuracy_hand_computed():
    assert accuracy(["A", "B", "C"], ["A", "B", "X"]) == pytest.approx(2 / 3)


def test_accuracy_rejects_empty():
    with pytest.raises(ValueError):
        accuracy([], [])


def test_error_rate_is_complement_of_accuracy():
    predictions, targets = ["A", "B", "C"], ["A", "B", "X"]
    assert error_rate(predictions, targets) == pytest.approx(1 - accuracy(predictions, targets))


def test_confusion_matrix_hand_computed():
    predictions = ["A", "A", "B", "C"]
    targets = ["A", "B", "B", "C"]
    cm = confusion_matrix(predictions, targets, LABELS)
    # rows = true label, cols = predicted label, in LABELS order [A, B, C]
    expected = np.array([[1, 0, 0], [1, 1, 0], [0, 0, 1]])
    np.testing.assert_array_equal(cm, expected)


def test_confusion_matrix_normalized_by_true_rows_sum_to_one():
    predictions = ["A", "A", "B", "C"]
    targets = ["A", "B", "B", "C"]
    cm = confusion_matrix(predictions, targets, LABELS)
    normalized = confusion_matrix_normalized(cm, by="true")
    row_sums = normalized.sum(axis=1)
    # row for "B" (2 cases) sums to 1; every non-empty row sums to 1
    assert row_sums[1] == pytest.approx(1.0)


def test_per_class_metrics_perfect_predictions():
    predictions = targets = ["A", "B", "C", "A", "B", "C"]
    cm = confusion_matrix(predictions, targets, LABELS)
    metrics = per_class_metrics(cm)
    np.testing.assert_array_almost_equal(metrics.precision, [1.0, 1.0, 1.0])
    np.testing.assert_array_almost_equal(metrics.recall, [1.0, 1.0, 1.0])
    np.testing.assert_array_almost_equal(metrics.f1, [1.0, 1.0, 1.0])


def test_per_class_metrics_specificity_and_npv_hand_computed():
    # Binary-flavored 2-class case is easiest to hand-verify.
    labels = ["POS", "NEG"]
    predictions = ["POS", "POS", "NEG", "NEG"]
    targets = ["POS", "NEG", "POS", "NEG"]
    cm = confusion_matrix(predictions, targets, labels)
    metrics = per_class_metrics(cm)
    # For "POS": tp=1, fp=1, fn=1, tn=1
    assert metrics.precision[0] == pytest.approx(0.5)
    assert metrics.recall[0] == pytest.approx(0.5)
    assert metrics.specificity[0] == pytest.approx(0.5)
    assert metrics.npv[0] == pytest.approx(0.5)


def test_macro_precision_recall_f1_perfect_predictions():
    predictions = targets = ["A", "B", "C"]
    cm = confusion_matrix(predictions, targets, LABELS)
    precision, recall, f1 = macro_precision_recall_f1(cm)
    assert (precision, recall, f1) == pytest.approx((1.0, 1.0, 1.0))


def test_weighted_precision_recall_f1_perfect_predictions():
    predictions = targets = ["A", "B", "C", "A"]
    precision, recall, f1 = weighted_precision_recall_f1(predictions, targets, LABELS)
    assert (precision, recall, f1) == pytest.approx((1.0, 1.0, 1.0))


def test_micro_precision_recall_f1_equals_accuracy_for_single_label_case():
    predictions = ["A", "B", "C", "A"]
    targets = ["A", "B", "B", "A"]
    cm = confusion_matrix(predictions, targets, LABELS)
    precision, recall, f1 = micro_precision_recall_f1(cm)
    # Micro-averaging in single-label multiclass collapses to accuracy.
    assert precision == pytest.approx(accuracy(predictions, targets))
    assert precision == recall == f1


def test_balanced_accuracy_handles_class_imbalance():
    # 9 "A"s all correct, 1 "B" wrong -> plain accuracy is 90%, but balanced
    # accuracy averages per-class recall, so it should be lower (50%: A=100%, B=0%).
    predictions = ["A"] * 9 + ["A"]
    targets = ["A"] * 9 + ["B"]
    assert accuracy(predictions, targets) == pytest.approx(0.9)
    assert balanced_accuracy(predictions, targets) == pytest.approx(0.5)


def test_matthews_correlation_coefficient_perfect_predictions():
    predictions = targets = ["A", "B", "C", "A", "B"]
    assert matthews_correlation_coefficient(predictions, targets) == pytest.approx(1.0)


def test_cohens_kappa_perfect_agreement():
    predictions = targets = ["A", "B", "C", "A", "B"]
    assert cohens_kappa(predictions, targets) == pytest.approx(1.0)


def test_top_k_accuracy_hand_computed():
    labels = ["A", "B", "C"]
    # true label "B" is the 2nd-highest probability -> counts for top-2, not top-1
    probabilities = np.array([[0.1, 0.3, 0.6]])
    targets = ["B"]
    assert top_k_accuracy(probabilities, targets, labels, k=1) == 0.0
    assert top_k_accuracy(probabilities, targets, labels, k=2) == 1.0


def _synthetic_probabilistic_case():
    labels = ["A", "B"]
    # Well-separated: high confidence and correct for the first 8, wrong for the last 2.
    targets = ["A"] * 5 + ["B"] * 5
    probabilities = np.array(
        [[0.9, 0.1]] * 5 + [[0.2, 0.8]] * 3 + [[0.7, 0.3]] * 2  # last two are wrong, mid-confidence
    )
    return labels, targets, probabilities


def test_roc_one_vs_rest_and_macro_auc_are_high_for_well_separated_classes():
    labels, targets, probabilities = _synthetic_probabilistic_case()
    per_class = roc_one_vs_rest(probabilities, targets, labels)
    assert per_class["A"].auc > 0.8
    auc = macro_auc(probabilities, targets, labels)
    assert auc is not None
    assert auc > 0.8


def test_macro_auc_unaffected_by_non_alphabetical_label_order():
    # Regression test: sklearn's roc_auc_score(multi_class="ovr") silently
    # assumes probability columns are sorted alphabetically by label,
    # regardless of the `labels` argument's actual order. "NORMAL" sorts
    # after "DCM"/"HCM" alphabetically but is declared first here (matching
    # this project's DiagnosisClass order) — a real bug this test guards
    # against regressing.
    labels = ["NORMAL", "DCM", "HCM"]
    targets = ["NORMAL"] * 5 + ["DCM"] * 5 + ["HCM"] * 5
    probabilities = np.array(
        [[0.9, 0.05, 0.05]] * 5 + [[0.05, 0.9, 0.05]] * 5 + [[0.05, 0.05, 0.9]] * 5
    )
    auc = macro_auc(probabilities, targets, labels)
    assert auc == pytest.approx(1.0)


def test_multiclass_log_loss_unaffected_by_non_alphabetical_label_order():
    labels = ["NORMAL", "DCM", "HCM"]
    targets = ["NORMAL", "NORMAL", "DCM", "HCM"]
    probabilities = np.array([[0.9, 0.05, 0.05]] * 2 + [[0.05, 0.9, 0.05]] + [[0.05, 0.05, 0.9]])
    loss = multiclass_log_loss(probabilities, targets, labels)
    assert loss == pytest.approx(-np.log(0.9), abs=1e-6)


def test_macro_auc_averages_only_over_classes_with_a_defined_auc():
    # "C" never occurs in targets, so its one-vs-rest AUC is undefined; the
    # macro average is still reported over "A"/"B" (which do have real data)
    # rather than the whole metric becoming None just because one class was
    # absent from this particular split.
    labels = ["A", "B", "C"]
    targets = ["A", "A", "B", "B"]
    probabilities = np.array([[0.6, 0.3, 0.1]] * 4)
    auc = macro_auc(probabilities, targets, labels)
    assert auc is not None
    per_class = roc_one_vs_rest(probabilities, targets, labels)
    assert "C" not in per_class
    assert auc == pytest.approx(np.mean([r.auc for r in per_class.values()]))


def test_macro_auc_none_when_every_class_is_absent_or_undefined():
    labels = ["A", "B"]
    targets = ["A", "A", "A"]  # "B" never occurs, and "A" is the only class present
    probabilities = np.array([[0.6, 0.4]] * 3)
    assert macro_auc(probabilities, targets, labels) is None


def test_micro_average_roc_runs_and_returns_valid_auc():
    labels, targets, probabilities = _synthetic_probabilistic_case()
    result = micro_average_roc(probabilities, targets, labels)
    assert 0.0 <= result.auc <= 1.0


def test_pr_curve_and_micro_pr_auc_high_for_well_separated_classes():
    labels, targets, probabilities = _synthetic_probabilistic_case()
    per_class = pr_curve_one_vs_rest(probabilities, targets, labels)
    assert per_class["A"].average_precision > 0.7
    assert micro_pr_auc(probabilities, targets, labels) > 0.7


def test_multiclass_brier_score_perfect_confident_predictions_is_zero():
    labels = ["A", "B"]
    targets = ["A", "B"]
    probabilities = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert multiclass_brier_score(probabilities, targets, labels) == pytest.approx(0.0)


def test_multiclass_brier_score_uniform_guessing_is_worse_than_confident_correct():
    labels = ["A", "B"]
    targets = ["A", "B"]
    confident_correct = np.array([[1.0, 0.0], [0.0, 1.0]])
    uniform = np.array([[0.5, 0.5], [0.5, 0.5]])
    assert multiclass_brier_score(uniform, targets, labels) > multiclass_brier_score(confident_correct, targets, labels)


def test_multiclass_log_loss_perfect_confident_predictions_near_zero():
    labels = ["A", "B"]
    targets = ["A", "B"]
    probabilities = np.array([[0.999, 0.001], [0.001, 0.999]])
    assert multiclass_log_loss(probabilities, targets, labels) < 0.01


def test_top1_reliability_diagram_perfectly_calibrated_case():
    # Every prediction at 0.8 confidence, and exactly 80% of them correct ->
    # ECE should be ~0 for the bin containing 0.8.
    confidences = [0.8] * 10
    correct = [True] * 8 + [False] * 2
    diagram = top1_reliability_diagram(confidences, correct, n_bins=10)
    assert diagram.ece == pytest.approx(0.0, abs=1e-6)


def test_top1_reliability_diagram_overconfident_case_has_positive_ece():
    confidences = [0.99] * 10
    correct = [True] * 5 + [False] * 5  # only 50% correct despite 99% confidence
    diagram = top1_reliability_diagram(confidences, correct, n_bins=10)
    assert diagram.ece > 0.3


def test_high_confidence_error_rate_hand_computed():
    confidences = [0.95, 0.95, 0.5]
    correct = [True, False, True]
    # Only the first two exceed the 0.9 threshold; one of those two is wrong.
    assert high_confidence_error_rate(confidences, correct, threshold=0.9) == pytest.approx(0.5)


def test_risk_coverage_curve_full_coverage_matches_plain_accuracy():
    labels, targets, probabilities = _synthetic_probabilistic_case()
    predictions = [labels[i] for i in probabilities.argmax(axis=1)]
    confidences = probabilities.max(axis=1)
    curve = risk_coverage_curve(predictions, targets, confidences, labels, coverage_steps=[1.0])
    assert curve[0].accuracy == pytest.approx(accuracy(predictions, targets))


def test_risk_coverage_curve_accuracy_improves_as_coverage_shrinks():
    labels, targets, probabilities = _synthetic_probabilistic_case()
    predictions = [labels[i] for i in probabilities.argmax(axis=1)]
    confidences = probabilities.max(axis=1)
    curve = risk_coverage_curve(predictions, targets, confidences, labels, coverage_steps=[1.0, 0.5])
    full_coverage_acc = curve[0].accuracy
    half_coverage_acc = curve[1].accuracy
    # Keeping only the most-confident half should never do worse than keeping everything.
    assert half_coverage_acc >= full_coverage_acc


def test_selective_accuracy_at_rejection_hand_computed():
    predictions = ["A", "A", "B", "B"]
    targets = ["A", "B", "B", "A"]  # 2/4 correct overall
    confidences = [0.99, 0.4, 0.99, 0.4]  # the two correct ones are the most confident
    assert selective_accuracy_at_rejection(predictions, targets, confidences, reject_fraction=0.5) == pytest.approx(1.0)
