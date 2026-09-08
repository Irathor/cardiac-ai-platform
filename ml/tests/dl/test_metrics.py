import torch

from cardiac_ai_ml.dl.metrics import (
    classification_accuracy,
    dice_score_per_class,
    mean_dice_excluding_background,
    per_class_f1,
)


def test_dice_score_perfect_prediction_is_all_ones():
    target = torch.tensor([[0, 1], [2, 3]])
    scores = dice_score_per_class(target, target, num_classes=4)
    assert scores == [1.0, 1.0, 1.0, 1.0]


def test_dice_score_completely_wrong_prediction_is_low():
    target = torch.zeros((4, 4), dtype=torch.long)
    target[1:3, 1:3] = 1
    prediction = torch.zeros((4, 4), dtype=torch.long)  # never predicts class 1
    scores = dice_score_per_class(prediction, target, num_classes=2)
    assert scores[1] < 0.1


def test_dice_score_absent_class_in_both_is_a_vacuous_match():
    target = torch.zeros((4, 4), dtype=torch.long)
    prediction = torch.zeros((4, 4), dtype=torch.long)
    scores = dice_score_per_class(prediction, target, num_classes=4)
    # Classes 1-3 appear in neither — a correct "nothing here" match, not 0.
    assert scores[1:] == [1.0, 1.0, 1.0]


def test_mean_dice_excluding_background_ignores_first_class():
    assert mean_dice_excluding_background([0.0, 1.0, 1.0, 1.0]) == 1.0


def test_classification_accuracy():
    assert classification_accuracy([1, 2, 3], [1, 2, 4]) == 2 / 3


def test_classification_accuracy_rejects_empty():
    import pytest

    with pytest.raises(ValueError):
        classification_accuracy([], [])


def test_per_class_f1_perfect_predictions():
    predictions = [0, 1, 2, 0, 1, 2]
    targets = [0, 1, 2, 0, 1, 2]
    scores = per_class_f1(predictions, targets, num_classes=3)
    assert scores == [1.0, 1.0, 1.0]


def test_per_class_f1_never_predicted_class_is_zero():
    predictions = [0, 0, 0]
    targets = [0, 1, 2]
    scores = per_class_f1(predictions, targets, num_classes=3)
    assert scores[1] == 0.0
    assert scores[2] == 0.0
