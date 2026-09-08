"""Agreement metrics between a biomarker computed from a PREDICTED
segmentation mask and the same biomarker computed from the REFERENCE
(ground-truth) mask — MAE/RMSE/bias/Bland-Altman/ICC/correlation, applied
per-biomarker (LVEDV, LVESV, LVEF, RVEDV, RVESV, RVEF, stroke volume,
myocardial mass) over a list of patients.

Pure numpy/scipy on paired (predicted, reference) float arrays — no
knowledge of masks, NIfTI, or which specific biomarker is being compared,
so the same functions serve every biomarker in `cardiac_ai_ml.biomarkers`.
"""
from dataclasses import dataclass

import numpy as np
from scipy import stats


def _as_arrays(predicted: list[float], reference: list[float]) -> tuple[np.ndarray, np.ndarray]:
    if len(predicted) != len(reference):
        raise ValueError("predicted and reference must have the same length")
    if not predicted:
        raise ValueError("cannot compute agreement metrics over zero paired values")
    return np.asarray(predicted, dtype=float), np.asarray(reference, dtype=float)


def mean_absolute_error(predicted: list[float], reference: list[float]) -> float:
    p, r = _as_arrays(predicted, reference)
    return float(np.mean(np.abs(p - r)))


def root_mean_squared_error(predicted: list[float], reference: list[float]) -> float:
    p, r = _as_arrays(predicted, reference)
    return float(np.sqrt(np.mean((p - r) ** 2)))


def mean_error(predicted: list[float], reference: list[float]) -> float:
    """Signed bias: positive means the model systematically over-estimates."""
    p, r = _as_arrays(predicted, reference)
    return float(np.mean(p - r))


def mean_absolute_percentage_error(predicted: list[float], reference: list[float]) -> float | None:
    """None (not a fabricated number) when every reference value is zero —
    MAPE is undefined, not infinite/zero, in that case."""
    p, r = _as_arrays(predicted, reference)
    nonzero = r != 0
    if not nonzero.any():
        return None
    return float(np.mean(np.abs((p[nonzero] - r[nonzero]) / r[nonzero])) * 100.0)


def pearson_correlation(predicted: list[float], reference: list[float]) -> float:
    p, r = _as_arrays(predicted, reference)
    if np.std(p) == 0 or np.std(r) == 0:
        return float("nan")  # correlation undefined with zero variance in either arm
    return float(stats.pearsonr(p, r).statistic)


def spearman_correlation(predicted: list[float], reference: list[float]) -> float:
    p, r = _as_arrays(predicted, reference)
    if np.std(p) == 0 or np.std(r) == 0:
        return float("nan")
    return float(stats.spearmanr(p, r).statistic)


def r_squared(predicted: list[float], reference: list[float]) -> float:
    p, r = _as_arrays(predicted, reference)
    ss_res = np.sum((r - p) ** 2)
    ss_tot = np.sum((r - np.mean(r)) ** 2)
    if ss_tot == 0:
        return float("nan")
    return float(1.0 - ss_res / ss_tot)


@dataclass(frozen=True)
class BlandAltmanResult:
    mean_difference: float
    sd_difference: float
    limit_of_agreement_lower: float
    limit_of_agreement_upper: float


def bland_altman(predicted: list[float], reference: list[float]) -> BlandAltmanResult:
    """Mean difference (bias) plus the classic 95% limits of agreement
    (mean ± 1.96·SD of the differences) — Bland & Altman 1986."""
    p, r = _as_arrays(predicted, reference)
    diff = p - r
    mean_diff = float(np.mean(diff))
    sd_diff = float(np.std(diff, ddof=1)) if len(diff) > 1 else 0.0
    return BlandAltmanResult(
        mean_difference=mean_diff,
        sd_difference=sd_diff,
        limit_of_agreement_lower=mean_diff - 1.96 * sd_diff,
        limit_of_agreement_upper=mean_diff + 1.96 * sd_diff,
    )


def intraclass_correlation(predicted: list[float], reference: list[float]) -> float:
    """ICC(2,1) — two-way random effects, single measurement, absolute
    agreement (Shrout & Fleiss 1979 / McGraw & Wong 1996 convention),
    treating "predicted" and "reference" as two raters measuring the same
    n subjects. Chosen over ICC(3,1)/consistency-only because a predicted
    biomarker that is perfectly correlated with but systematically biased
    from the reference should NOT score as perfect agreement — unlike
    Pearson r, ICC(2,1) penalizes that bias.

    NaN (not a fabricated number) when every subject has p==r exactly AND
    all subjects are identical to each other (zero total variance — the
    ANOVA decomposition below is 0/0), or more generally whenever MSR+MSE
    is degenerate.
    """
    p, r = _as_arrays(predicted, reference)
    n = len(p)
    if n < 2:
        return float("nan")
    k = 2  # two "raters": predicted, reference
    data = np.stack([p, r], axis=1)  # (n, k)

    grand_mean = data.mean()
    row_means = data.mean(axis=1)
    col_means = data.mean(axis=0)

    ss_total = np.sum((data - grand_mean) ** 2)
    ss_rows = k * np.sum((row_means - grand_mean) ** 2)
    ss_cols = n * np.sum((col_means - grand_mean) ** 2)
    ss_error = ss_total - ss_rows - ss_cols

    ms_rows = ss_rows / (n - 1)
    ms_cols = ss_cols / (k - 1)
    ms_error = ss_error / ((n - 1) * (k - 1))

    denominator = ms_rows + (k - 1) * ms_error + k * (ms_cols - ms_error) / n
    if denominator == 0:
        return float("nan")
    return float((ms_rows - ms_error) / denominator)
