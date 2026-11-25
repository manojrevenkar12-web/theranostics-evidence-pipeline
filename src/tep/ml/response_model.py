"""PSA50 response from baseline imaging and PSA: a pre-specified logistic model, validated leave-site-out,
explained with SHAP. A gradient-boosted model is reported alongside as a secondary analysis."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import shap
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from tep import config
from tep.stats.diagnostic import delong, recalibrate


@dataclass
class ModelResult:
    n: int
    positives: int
    auc: float = math.nan
    auc_lo: float = math.nan
    auc_hi: float = math.nan
    calibration_slope: float = math.nan
    calibration_intercept: float = math.nan
    brier: float = math.nan
    gb_auc: float = math.nan
    shap_mean_abs: dict[str, float] = field(default_factory=dict)
    coefficients: dict[str, float] = field(default_factory=dict)
    sites: int = 0


def _logistic(seed: int):
    return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=2000, random_state=seed))


def fit_evaluate(table: pd.DataFrame) -> ModelResult:
    """table: one row per patient with feature columns, 'label' (0/1) and 'site'."""
    sap = config.load("sap")["model"]
    feats = sap["features"]
    seed = sap["seed"]
    t = table.dropna(subset=[*feats, "label"]).reset_index(drop=True)
    res = ModelResult(len(t), int(t["label"].sum()) if len(t) else 0, sites=t["site"].nunique() if len(t) else 0)
    if len(t) < 20 or t["label"].nunique() < 2 or t["site"].nunique() < 2:
        return res
    oof = np.full(len(t), np.nan)
    oof_gb = np.full(len(t), np.nan)
    for site in sorted(t["site"].unique()):
        test = t["site"] == site
        train = ~test
        if t.loc[train, "label"].nunique() < 2:
            continue
        m = _logistic(seed).fit(t.loc[train, feats], t.loc[train, "label"])
        oof[test.values] = m.predict_proba(t.loc[test, feats])[:, 1]
        gb = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.08, max_iter=150, random_state=seed)
        gb.fit(t.loc[train, feats], t.loc[train, "label"])
        oof_gb[test.values] = gb.predict_proba(t.loc[test, feats])[:, 1]
    ok = ~np.isnan(oof)
    y = t["label"].to_numpy()[ok]
    res.auc, _, res.auc_lo, res.auc_hi = delong(y, oof[ok])
    cal = recalibrate(y, oof[ok])
    res.calibration_slope, res.calibration_intercept, res.brier = cal["slope"], cal["intercept"], cal["brier"]
    okg = ~np.isnan(oof_gb)
    res.gb_auc = delong(t["label"].to_numpy()[okg], oof_gb[okg])[0]
    final = _logistic(seed).fit(t[feats], t["label"])
    scaler, lr = final[0], final[1]
    x = scaler.transform(t[feats])
    explainer = shap.LinearExplainer(lr, shap.maskers.Independent(x, max_samples=len(x)))
    sv = explainer.shap_values(x)
    res.shap_mean_abs = {f: float(np.abs(sv[:, i]).mean()) for i, f in enumerate(feats)}
    res.coefficients = {f: float(c) for f, c in zip(feats, lr.coef_[0], strict=True)}
    res.auc, res.auc_lo, res.auc_hi = float(res.auc), float(res.auc_lo), float(res.auc_hi)
    return res
