""""Smoke training" for the nearest-prototype classifier (see
docs/phases.md — Phase 7 is deliberately a lightweight, real-but-trivial
training job, not a deep-learning pipeline this environment has no data or
GPU to run).

`fit_nearest_centroid` is a genuine, well-known algorithm (nearest-centroid /
nearest-mean classifier): each class's prototype is the mean feature vector
of its own training examples, computed from real data instead of the
hand-picked profiles `classification.classify_demo` uses. The two are
interchangeable — `classify_with_prototypes` is what both ultimately call.
"""
from dataclasses import dataclass

from .classification import FEATURE_NAMES, Prototypes, classify_with_prototypes


@dataclass(frozen=True)
class TrainingCase:
    features: dict[str, float]
    label: str


class EmptyTrainingSetError(ValueError):
    pass


class MissingClassError(ValueError):
    pass


def fit_nearest_centroid(cases: list[TrainingCase], class_labels: set[str]) -> Prototypes:
    if not cases:
        raise EmptyTrainingSetError("cannot fit a model with zero training cases")

    sums: dict[str, dict[str, float]] = {label: dict.fromkeys(FEATURE_NAMES, 0.0) for label in class_labels}
    counts: dict[str, int] = dict.fromkeys(class_labels, 0)

    for case in cases:
        if case.label not in sums:
            raise MissingClassError(f"training case has an unexpected label: {case.label!r}")
        counts[case.label] += 1
        for name in FEATURE_NAMES:
            sums[case.label][name] += case.features[name]

    missing = [label for label, count in counts.items() if count == 0]
    if missing:
        raise MissingClassError(f"no training cases for class(es): {sorted(missing)}")

    return {
        label: {name: sums[label][name] / counts[label] for name in FEATURE_NAMES}
        for label in class_labels
    }


@dataclass(frozen=True)
class EvaluationResult:
    accuracy: float
    case_count: int
    correct_count: int
    per_class_accuracy: dict[str, float]


def evaluate(prototypes: Prototypes, cases: list[TrainingCase]) -> EvaluationResult:
    if not cases:
        raise EmptyTrainingSetError("cannot evaluate a model with zero cases")

    correct = 0
    per_class_correct: dict[str, int] = {}
    per_class_total: dict[str, int] = {}
    for case in cases:
        predicted = classify_with_prototypes(case.features, prototypes).predicted_class
        per_class_total[case.label] = per_class_total.get(case.label, 0) + 1
        if predicted == case.label:
            correct += 1
            per_class_correct[case.label] = per_class_correct.get(case.label, 0) + 1

    return EvaluationResult(
        accuracy=correct / len(cases),
        case_count=len(cases),
        correct_count=correct,
        per_class_accuracy={
            label: per_class_correct.get(label, 0) / total for label, total in per_class_total.items()
        },
    )
