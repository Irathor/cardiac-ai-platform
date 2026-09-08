import numpy as np
import pytest

from cardiac_ai_ml.dl.fold_stats import bootstrap_ci, summarize


def test_summarize_basic_stats():
    result = summarize([1.0, 2.0, 3.0, 4.0, 5.0])
    assert result.mean == 3.0
    assert result.median == 3.0
    assert result.minimum == 1.0
    assert result.maximum == 5.0
    assert result.std == pytest.approx(np.std([1, 2, 3, 4, 5], ddof=1))


def test_summarize_single_value_has_zero_std():
    result = summarize([7.0])
    assert result.mean == 7.0
    assert result.std == 0.0


def test_summarize_rejects_empty():
    with pytest.raises(ValueError):
        summarize([])


def test_bootstrap_ci_constant_statistic_is_a_point_interval():
    low, high = bootstrap_ci(10, lambda idx: 5.0, n_resamples=100, seed=1)
    assert low == 5.0
    assert high == 5.0


def test_bootstrap_ci_brackets_the_true_mean_for_a_known_distribution():
    rng = np.random.default_rng(0)
    data = rng.normal(loc=10.0, scale=1.0, size=500)

    def statistic(indices: np.ndarray) -> float:
        return float(np.mean(data[indices]))

    low, high = bootstrap_ci(len(data), statistic, n_resamples=1000, seed=2)
    assert low < 10.0 < high
