"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import comb

import numpy as np
from scipy import stats

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def _check_lengths(human: Sequence[str], judge: Sequence[str]) -> None:
    if len(human) != len(judge):
        raise ValueError(
            f"human and judge must have the same length ({len(human)} != {len(judge)})"
        )


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    _check_lengths(human, judge)
    tp = fp = fn = tn = 0
    for h, j in zip(human, judge):
        h_pos = h == POS
        j_pos = j == POS
        if h_pos and j_pos:
            tp += 1
        elif not h_pos and j_pos:
            fp += 1
        elif h_pos and not j_pos:
            fn += 1
        else:
            tn += 1
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn}


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    c = confusion(human, judge)
    tp, fp, fn = c["tp"], c["fp"], c["fn"]
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return precision, recall


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    _check_lengths(human, judge)
    n = len(human)
    if n == 0:
        raise ValueError("kappa is undefined for empty input")

    c = confusion(human, judge)
    tp, fp, fn, tn = c["tp"], c["fp"], c["fn"], c["tn"]

    p_o = (tp + tn) / n
    # marginal probabilities of the positive / negative label for each rater
    h_pos = (tp + fn) / n
    j_pos = (tp + fp) / n
    p_e = h_pos * j_pos + (1 - h_pos) * (1 - j_pos)

    if np.isclose(p_e, 1.0):
        raise ValueError("kappa is undefined (p_e == 1): constant rater(s), no signal")
    return float((p_o - p_e) / (1 - p_e))


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1]."""
    denom = sensitivity + specificity - 1
    if denom == 0:
        raise ValueError(
            "Rogan-Gladen undefined: sensitivity + specificity == 1 (judge is no better than chance)"
        )
    est = (observed_rate + specificity - 1) / denom
    return float(min(1.0, max(0.0, est)))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    if a_arr.shape != b_arr.shape:
        raise ValueError(
            f"a and b must be paired (same length): {a_arr.shape} != {b_arr.shape}"
        )
    if a_arr.size == 0:
        raise ValueError("paired_bootstrap needs at least one item")

    if np.array_equal(a_arr, b_arr):
        return (0.0, 0.0, 0.0)

    def _mean_diff(x, y, axis=-1):
        return np.mean(x, axis=axis) - np.mean(y, axis=axis)

    res = stats.bootstrap(
        (a_arr, b_arr),
        _mean_diff,
        paired=True,
        vectorized=True,
        n_resamples=n_resamples,
        confidence_level=confidence,
        method="percentile",
        rng=np.random.default_rng(rng),
    )
    point = float(np.mean(a_arr) - np.mean(b_arr))
    return point, float(res.confidence_interval.low), float(res.confidence_interval.high)


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    if n < 1 or c < 0 or c > n or k < 1 or k > n:
        raise ValueError(f"invalid (n, c, k) = ({n}, {c}, {k})")
    if n - c < k:
        # fewer than k failures: any draw of k must contain a pass
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    if n < 1 or c < 0 or c > n or k < 1 or k > n:
        raise ValueError(f"invalid (n, c, k) = ({n}, {c}, {k})")
    return comb(c, k) / comb(n, k)