"""Statistics for diagnostic performance, agreement and discrimination, with intervals that respect clustering."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence

import numpy as np
from scipy import stats as st

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float, float]:
    """Proportion with Wilson score interval."""
    if n == 0:
        return math.nan, math.nan, math.nan
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return p, max(0.0, c - h), min(1.0, c + h)


def cluster_bootstrap(clusters: Sequence[tuple[float, float]], b: int, seed: int) -> tuple[float, float, float]:
    """Ratio estimate sum(num)/sum(den) over clusters (e.g. lesions within patients), percentile CI by resampling clusters."""
    arr = np.asarray(clusters, dtype=float)
    if len(arr) == 0 or arr[:, 1].sum() == 0:
        return math.nan, math.nan, math.nan
    est = arr[:, 0].sum() / arr[:, 1].sum()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(arr), size=(b, len(arr)))
    num = arr[idx, 0].sum(axis=1)
    den = arr[idx, 1].sum(axis=1)
    reps = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
    lo, hi = np.nanpercentile(reps, [2.5, 97.5])
    return float(est), float(lo), float(hi)


def mean_bootstrap(values: Sequence[float], b: int, seed: int) -> tuple[float, float, float]:
    return cluster_bootstrap([(v, 1.0) for v in values], b, seed)


def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    labels = sorted(set(a) | set(b))
    if len(a) == 0:
        return math.nan
    n = len(a)
    po = sum(x == y for x, y in zip(a, b, strict=True)) / n
    pe = sum((list(a).count(lab) / n) * (list(b).count(lab) / n) for lab in labels)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def _midrank(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x)
    xs = x[order]
    n = len(x)
    t = np.zeros(n)
    i = 0
    while i < n:
        j = i
        while j < n and xs[j] == xs[i]:
            j += 1
        t[i:j] = 0.5 * (i + j - 1) + 1
        i = j
    out = np.empty(n)
    out[order] = t
    return out


def delong(y: Sequence[int], score: Sequence[float]) -> tuple[float, float, float, float]:
    """AUC with DeLong standard error and 95% CI (logit-free, clipped to [0, 1])."""
    ya = np.asarray(y, dtype=int)
    sa = np.asarray(score, dtype=float)
    pos, neg = sa[ya == 1], sa[ya == 0]
    m, n = len(pos), len(neg)
    if m == 0 or n == 0:
        return math.nan, math.nan, math.nan, math.nan
    tx, ty, tz = _midrank(pos), _midrank(neg), _midrank(np.concatenate([pos, neg]))
    auc = (tz[:m].sum() - m * (m + 1) / 2) / (m * n)
    v01 = (tz[:m] - tx) / n
    v10 = 1 - (tz[m:] - ty) / m
    var = np.var(v01, ddof=1) / m + np.var(v10, ddof=1) / n if m > 1 and n > 1 else 0.0
    se = math.sqrt(max(var, 0.0))
    return float(auc), se, max(0.0, auc - Z95 * se), min(1.0, auc + Z95 * se)


def holm(p: Sequence[float]) -> list[float]:
    """Holm-adjusted p-values."""
    order = np.argsort(np.asarray(p, float))
    k = len(p)
    adj = np.empty(k)
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (k - rank) * p[i]))
        adj[i] = running
    return [float(x) for x in adj]


def bland_altman(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    d = np.asarray(a, float) - np.asarray(b, float)
    bias = float(d.mean())
    sd = float(d.std(ddof=1)) if len(d) > 1 else 0.0
    return bias, bias - Z95 * sd, bias + Z95 * sd


def recalibrate(y_in: Sequence[int], p_in: Sequence[float]) -> dict[str, float]:
    y = np.asarray(y_in, int)
    p = np.clip(np.asarray(p_in, float), 1e-6, 1 - 1e-6)
    x = np.log(p / (1 - p))
    a, b = 0.0, 1.0
    for _ in range(50):  # Newton-Raphson for logit(P(y=1)) = a + b*x
        eta = np.clip(a + b * x, -30, 30)
        mu = 1 / (1 + np.exp(-eta))
        w = mu * (1 - mu) + 1e-12
        g = np.array([np.sum(y - mu), np.sum((y - mu) * x)])
        h = np.array([[np.sum(w), np.sum(w * x)], [np.sum(w * x), np.sum(w * x * x)]])
        try:
            step = np.linalg.solve(h, g)
        except np.linalg.LinAlgError:
            break
        norm = float(np.abs(step).max())
        if norm > 1.0:
            step = step / norm  # damped: a model worse than chance can push the slope off to infinity
        a, b = a + step[0], b + step[1]
        if np.abs(step).max() < 1e-9:
            break
    return {"brier": float(np.mean((p - y) ** 2)), "intercept": float(a), "slope": float(b)}


def proportion_test(k1: int, n1: int, k2: int, n2: int) -> float:
    """Two-sided p-value for a difference in proportions (Fisher's exact test)."""
    return float(st.fisher_exact([[k1, n1 - k1], [k2, n2 - k2]])[1])


def summarise(f: Callable[..., tuple[float, float, float]], *a: object) -> dict[str, float]:
    est, lo, hi = f(*a)
    return {"estimate": est, "lo": lo, "hi": hi}
