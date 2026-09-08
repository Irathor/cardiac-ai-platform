import math

import numpy as np
import pytest

from cardiac_ai_ml.dl.biomarker_metrics import (
    bland_altman,
    intraclass_correlation,
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_error,
    pearson_correlation,
    r_squared,
    root_mean_squared_error,
    spearman_correlation,
)


def test_mean_absolute_error_hand_computed():
    assert mean_absolute_error([1.0, 2.0, 3.0], [1.0, 4.0, 3.0]) == pytest.approx(2.0 / 3.0)


def test_root_mean_squared_error_hand_computed():
    assert root_mean_squared_error([0.0, 0.0], [3.0, 4.0]) == pytest.approx(math.sqrt((9 + 16) / 2))


def test_mean_error_is_signed_bias():
    assert mean_error([12.0, 8.0], [10.0, 10.0]) == pytest.approx(0.0)
    assert mean_error([15.0, 15.0], [10.0, 10.0]) == pytest.approx(5.0)


def test_mape_hand_computed():
    assert mean_absolute_percentage_error([110.0], [100.0]) == pytest.approx(10.0)


def test_mape_undefined_when_all_reference_zero():
    assert mean_absolute_percentage_error([5.0], [0.0]) is None


def test_pearson_correlation_perfect_linear_relationship():
    assert pearson_correlation([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)


def test_spearman_correlation_perfect_monotonic_nonlinear_relationship():
    assert spearman_correlation([1, 2, 3, 4], [1, 4, 9, 16]) == pytest.approx(1.0)


def test_r_squared_perfect_prediction_is_one():
    assert r_squared([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_bland_altman_hand_computed():
    predicted = [10.0, 13.0, 12.0]
    reference = [9.0, 11.0, 13.0]
    # differences: +1, +2, -1 -> mean = 2/3
    result = bland_altman(predicted, reference)
    assert result.mean_difference == pytest.approx(2 / 3)
    assert result.limit_of_agreement_lower < result.mean_difference < result.limit_of_agreement_upper


def test_bland_altman_zero_variance_differences_gives_a_point_interval():
    predicted = [10.0, 12.0, 14.0]
    reference = [9.0, 11.0, 13.0]  # every difference is exactly 1.0
    result = bland_altman(predicted, reference)
    assert result.mean_difference == pytest.approx(1.0)
    assert result.limit_of_agreement_lower == pytest.approx(1.0)
    assert result.limit_of_agreement_upper == pytest.approx(1.0)


def test_icc_perfect_identity_is_exactly_one():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert intraclass_correlation(values, values) == pytest.approx(1.0)


def test_icc_penalizes_systematic_bias_unlike_pearson():
    reference = [10.0, 20.0, 30.0, 40.0, 50.0]
    predicted = [x + 10.0 for x in reference]  # perfectly correlated, but biased
    icc = intraclass_correlation(predicted, reference)
    r = pearson_correlation(predicted, reference)
    assert r == pytest.approx(1.0)
    assert icc < r


def test_icc_near_zero_for_unrelated_random_data():
    rng = np.random.default_rng(0)
    predicted = rng.normal(size=200).tolist()
    reference = rng.normal(size=200).tolist()
    icc = intraclass_correlation(predicted, reference)
    assert abs(icc) < 0.3


def test_rejects_mismatched_lengths():
    with pytest.raises(ValueError):
        mean_absolute_error([1.0, 2.0], [1.0])


def test_rejects_empty_input():
    with pytest.raises(ValueError):
        mean_absolute_error([], [])
