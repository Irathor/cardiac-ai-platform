"""Evaluation metrics. Dice score is computed per-class then averaged
(macro), so a model that nails the large background class but misses the
much smaller RV cavity can't hide behind an inflated pixel-accuracy number.
"""
import numpy as np
import torch


def dice_score_per_class(prediction: torch.Tensor, target: torch.Tensor, num_classes: int, eps: float = 1e-6) -> list[float]:
    """`prediction` and `target` are (H, W) or (N, H, W) integer label maps
    (already argmaxed — not logits)."""
    scores = []
    for cls in range(num_classes):
        pred_mask = prediction == cls
        target_mask = target == cls
        intersection = (pred_mask & target_mask).sum().item()
        denom = pred_mask.sum().item() + target_mask.sum().item()
        if denom == 0:
            # Neither predicted nor present — a vacuous but correct match,
            # not a failure (matters for RV/LV/myo classes absent from a slice).
            scores.append(1.0)
        else:
            scores.append((2.0 * intersection + eps) / (denom + eps))
    return scores


def mean_dice_excluding_background(dice_per_class: list[float]) -> float:
    """The metric that actually matters clinically: how well the heart
    structures are segmented, not the (trivially easy) background class."""
    foreground = dice_per_class[1:]
    return float(np.mean(foreground)) if foreground else 0.0


def classification_accuracy(predictions: list[int], targets: list[int]) -> float:
    if not predictions:
        raise ValueError("cannot compute accuracy over zero predictions")
    correct = sum(p == t for p, t in zip(predictions, targets, strict=True))
    return correct / len(predictions)


def per_class_f1(predictions: list[int], targets: list[int], num_classes: int) -> list[float]:
    scores = []
    for cls in range(num_classes):
        tp = sum(p == cls and t == cls for p, t in zip(predictions, targets, strict=True))
        fp = sum(p == cls and t != cls for p, t in zip(predictions, targets, strict=True))
        fn = sum(p != cls and t == cls for p, t in zip(predictions, targets, strict=True))
        if tp + fp == 0 or tp + fn == 0:
            scores.append(0.0)
            continue
        precision = tp / (tp + fp)
        recall = tp / (tp + fn)
        scores.append(0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall))
    return scores
