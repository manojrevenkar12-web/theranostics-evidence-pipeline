import numpy as np
from sklearn.metrics import roc_auc_score

from tep.stats.diagnostic import cluster_bootstrap, cohen_kappa, delong, holm, recalibrate, wilson


def test_wilson_matches_reference():
    p, lo, hi = wilson(45, 50)
    assert round(lo, 4) == 0.7864 and round(hi, 4) == 0.9565


def test_delong_auc_equals_sklearn_and_ci_brackets_it():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 400)
    s = y + rng.normal(0, 1.2, 400)
    auc, se, lo, hi = delong(y, s)
    assert abs(auc - roc_auc_score(y, s)) < 1e-12
    assert lo < auc < hi and 0 < se < 0.05


def test_kappa_and_holm():
    assert cohen_kappa(list("aabb"), list("aabb")) == 1.0
    assert abs(cohen_kappa(list("aabbc"), list("aabcc")) - 0.70588) < 1e-4
    assert holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06]


def test_recalibration_of_a_calibrated_model_has_slope_near_one():
    rng = np.random.default_rng(1)
    x = rng.normal(0, 1.5, 5000)
    p = 1 / (1 + np.exp(-x))
    y = (rng.random(5000) < p).astype(int)
    r = recalibrate(y, p)
    assert abs(r["slope"] - 1) < 0.1 and abs(r["intercept"]) < 0.1


def test_cluster_bootstrap_is_wider_than_ignoring_clusters():
    clusters = [(10, 10)] * 20 + [(0, 10)] * 5  # all-or-nothing patients
    est, lo, hi = cluster_bootstrap(clusters, 2000, 3)
    k, n = 200, 250
    _, wlo, whi = wilson(k, n)
    assert abs(est - 0.8) < 1e-9 and (hi - lo) > (whi - wlo)
