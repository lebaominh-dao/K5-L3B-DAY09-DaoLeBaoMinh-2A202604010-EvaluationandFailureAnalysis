"""Statistics students implement (M2 judge calibration, M4 paired bootstrap).

Rules: a judge is a classifier -- measure it like one. A higher mean is not
"better" until the paired CI of the difference excludes 0.
Reference values to self-check are in tests/test_lab9_stats.py.
"""

from __future__ import annotations

import operator
from collections.abc import Sequence
from math import comb

POS = "FAIL"   # the judge's job is to FIND failures, so FAIL is the positive class


def confusion(human: Sequence[str], judge: Sequence[str]) -> dict[str, int]:
    """tp/fp/fn/tn with FAIL as positive."""
    if len(human) != len(judge):
        raise ValueError(f"length mismatch: {len(human)} human vs {len(judge)} judge labels")
    cm = {"tp": 0, "fp": 0, "fn": 0, "tn": 0}
    for h, j in zip(human, judge):
        h_pos, j_pos = h == POS, j == POS
        if j_pos:
            cm["tp" if h_pos else "fp"] += 1
        else:
            cm["fn" if h_pos else "tn"] += 1
    return cm


def precision_recall(human: Sequence[str], judge: Sequence[str]) -> tuple[float, float]:
    cm = confusion(human, judge)
    p_den, r_den = cm["tp"] + cm["fp"], cm["tp"] + cm["fn"]
    return (cm["tp"] / p_den if p_den else 0.0, cm["tp"] / r_den if r_den else 0.0)


def cohen_kappa(human: Sequence[str], judge: Sequence[str]) -> float:
    """kappa = (p_o - p_e) / (1 - p_e). Raise ValueError when undefined (p_e == 1):
    a constant judge has no signal and must FAIL calibration, not pass on a technicality."""
    cm = confusion(human, judge)
    n = sum(cm.values())
    if n == 0:
        raise ValueError("kappa undefined: no labels")
    p_o = (cm["tp"] + cm["tn"]) / n
    # chance agreement: both say FAIL by chance + both say PASS by chance
    h_fail, j_fail = (cm["tp"] + cm["fn"]) / n, (cm["tp"] + cm["fp"]) / n
    p_e = h_fail * j_fail + (1 - h_fail) * (1 - j_fail)
    if p_e >= 1:
        raise ValueError("kappa undefined: p_e == 1 (both raters constant)")
    return (p_o - p_e) / (1 - p_e)


def rogan_gladen(observed_rate: float, sensitivity: float, specificity: float) -> float:
    """Correct an observed failure rate for judge error; clip to [0, 1].
    Returns NaN when sens + spec <= 1: such a judge is no better than chance, so no correction exists."""
    denom = sensitivity + specificity - 1
    if denom <= 0:
        return float("nan")
    return min(1.0, max(0.0, (observed_rate + specificity - 1) / denom))


def paired_bootstrap(a: Sequence[float], b: Sequence[float], *, n_resamples: int = 1000,
                     rng: int = 2027, confidence: float = 0.95) -> tuple[float, float, float]:
    """a[i], b[i] = per-item mean over seeds, SAME items, SAME order.
    Return (mean(a)-mean(b), lo, hi) with scipy.stats.bootstrap(paired=True, method="percentile",
    rng=numpy.random.default_rng(rng)). If a == b everywhere return (0.0, 0.0, 0.0)."""
    import numpy as np
    from scipy.stats import bootstrap

    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if x.shape != y.shape:
        raise ValueError(f"paired samples must have the same length: {len(x)} vs {len(y)}")
    if np.array_equal(x, y):
        return (0.0, 0.0, 0.0)
    delta = float(x.mean() - y.mean())
    diffs = x - y
    if np.all(diffs == diffs[0]):   # constant difference: every resample gives the same delta
        return (delta, delta, delta)

    def mean_diff(xs, ys, axis=-1):
        return np.mean(xs, axis=axis) - np.mean(ys, axis=axis)

    res = bootstrap((x, y), mean_diff, paired=True, vectorized=True, n_resamples=n_resamples,
                    confidence_level=confidence, method="percentile",
                    rng=np.random.default_rng(rng))
    return (delta, float(res.confidence_interval.low), float(res.confidence_interval.high))


def pass_at_k(n: int, c: int, k: int) -> float:
    """Probability that AT LEAST ONE of k trials drawn from n (c of them passing) passes.
    Unbiased estimator (Chen et al. 2021): 1 - C(n-c, k) / C(n, k). Raise ValueError if k > n."""
    n, c, k = _check_nck(n, c, k)
    if n - c < k:            # every k-subset contains at least one passing trial
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """pass^k (tau-bench, Yao et al. 2024): probability that ALL k trials drawn from n pass.
    Unbiased estimator: C(c, k) / C(n, k). Raise ValueError if k > n.
    pass^k <= pass@1 <= pass@k; a reliable agent keeps pass^k close to pass@1."""
    n, c, k = _check_nck(n, c, k)
    return comb(c, k) / comb(n, k)   # comb(c, k) == 0 when c < k


def _check_nck(n: int, c: int, k: int) -> tuple[int, int, int]:
    """n trials, c of them passing, k drawn: integers with 0 <= c <= n and 1 <= k <= n.
    Anything else is a caller bug (wrong column, k larger than the runs we have), not a 0.0."""
    try:
        n, c, k = (operator.index(x) for x in (n, c, k))
    except TypeError as e:
        raise ValueError(f"n, c, k must be integers, got {(n, c, k)!r}") from e
    if n < 1:
        raise ValueError(f"need at least one trial, got n={n}")
    if not 0 <= c <= n:
        raise ValueError(f"c must be in [0, n={n}], got c={c}")
    if not 1 <= k <= n:
        raise ValueError(f"k must be in [1, n={n}], got k={k}")
    return n, c, k
