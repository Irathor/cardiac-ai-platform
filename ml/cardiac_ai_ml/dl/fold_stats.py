"""Cross-fold/cross-seed dispersion summaries — the honest way to report a
metric measured across k folds (or k random seeds) instead of a single
number that hides how much it actually varies.
"""
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DispersionSummary:
    mean: float
    std: float
    median: float
    iqr: float
    minimum: float
    maximum: float


def summarize(values: list[float]) -> DispersionSummary:
    if not values:
        raise ValueError("cannot summarize zero values")
    arr = np.asarray(values, dtype=float)
    q1, q3 = np.percentile(arr, [25, 75])
    return DispersionSummary(
        mean=float(np.mean(arr)),
        std=float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
        median=float(np.median(arr)),
        iqr=float(q3 - q1),
        minimum=float(np.min(arr)),
        maximum=float(np.max(arr)),
    )


def bootstrap_ci(
    n_items: int, statistic_fn: Callable[[np.ndarray], float], *, n_resamples: int = 2000, ci: float = 0.95, seed: int = 42
) -> tuple[float, float]:
    """Generic patient-level bootstrap: `statistic_fn(indices)` computes the
    metric of interest over a (possibly repeated) set of item indices, so
    callers can resample predictions/targets/probabilities (classification)
    or per-patient scores (segmentation/biomarkers) together without this
    function needing to know their shape. Returns the (low, high) percentile
    interval."""
    rng = np.random.default_rng(seed)
    values = np.empty(n_resamples)
    for i in range(n_resamples):
        indices = rng.integers(0, n_items, size=n_items)
        values[i] = statistic_fn(indices)
    alpha = (1 - ci) / 2
    return float(np.quantile(values, alpha)), float(np.quantile(values, 1 - alpha))
