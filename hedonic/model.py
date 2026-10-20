"""Hedonic regressions on log nightly rate with property-clustered standard errors.

OLS and the cluster-robust (CR1) variance are written out in numpy so every
step can be inspected; tests cross-check the result against statsmodels.

Three specifications:
- naive:      log rate on the amenities only (shows why controls matter).
- between:    property-level pool premium, identified ACROSS properties, with
              property, location, room, rate-plan and stay-date controls.
              Property fixed effects cannot be used here: a property either
              has a pool or not, so its fixed effect would absorb the pool.
- within:     room-level jacuzzi premium, identified WITHIN properties via
              property fixed effects plus stay-date fixed effects.
Standard errors are clustered by property in all three, because quotes from
the same property share unobserved quality and are not independent.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

CONTROLS_BETWEEN = ["stars", "review_score", "sea_km", "log_room_size", "non_refundable"]
FE_BETWEEN = ["locality", "room_type", "meal_plan", "stay_date"]
CONTROLS_WITHIN = ["log_room_size", "non_refundable"]
FE_WITHIN = ["property_id", "room_type", "meal_plan", "stay_date"]

SPECS = {
    "naive": {"terms": ["has_pool", "room_jacuzzi"], "fe": []},
    "between": {"terms": ["has_pool", "room_jacuzzi"] + CONTROLS_BETWEEN, "fe": FE_BETWEEN},
    "within": {"terms": ["room_jacuzzi"] + CONTROLS_WITHIN, "fe": FE_WITHIN},
}


@dataclass
class FitResult:
    spec: str
    names: list
    coef: np.ndarray
    se: np.ndarray
    n_obs: int
    n_clusters: int
    n_params: int
    r2: float

    def row(self, term: str, level: float = 0.95) -> dict:
        i = self.names.index(term)
        b, s = float(self.coef[i]), float(self.se[i])
        tcrit = stats.t.ppf(0.5 + level / 2, df=self.n_clusters - 1)
        lo, hi = b - tcrit * s, b + tcrit * s
        p = 2 * stats.t.sf(abs(b / s), df=self.n_clusters - 1)
        return {
            "spec": self.spec, "term": term, "coef_log": b, "se_cluster": s, "p_value": p,
            "premium_pct": 100 * (np.exp(b) - 1),
            "ci_low_pct": 100 * (np.exp(lo) - 1), "ci_high_pct": 100 * (np.exp(hi) - 1),
            "n_obs": self.n_obs, "n_clusters": self.n_clusters, "r2": self.r2,
        }


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["log_room_size"] = np.log(out["room_size_m2"])
    if "log_rate" not in out:
        out["log_rate"] = np.log(out["nightly_rate_eur"])
    return out


def design(df: pd.DataFrame, terms: list, fe: list) -> tuple[np.ndarray, list]:
    parts = [pd.DataFrame({"const": 1.0}, index=df.index), df[terms].astype(float)]
    for col in fe:
        parts.append(pd.get_dummies(df[col].astype(str), prefix=col, drop_first=True, dtype=float))
    X = pd.concat(parts, axis=1)
    return X.to_numpy(), list(X.columns)


def ols_cluster(y: np.ndarray, X: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """OLS coefficients and CR1 cluster-robust standard errors."""
    n, k = X.shape
    xtx_inv = np.linalg.pinv(X.T @ X)
    beta = xtx_inv @ X.T @ y
    resid = y - X @ beta
    meat = np.zeros((k, k))
    uniq = np.unique(groups)
    for g in uniq:
        m = groups == g
        s = X[m].T @ resid[m]
        meat += np.outer(s, s)
    G = len(uniq)
    correction = (G / (G - 1)) * ((n - 1) / (n - k))
    vcov = correction * xtx_inv @ meat @ xtx_inv
    r2 = 1 - (resid @ resid) / np.sum((y - y.mean()) ** 2)
    return beta, np.sqrt(np.diag(vcov)), float(r2)


def fit(df: pd.DataFrame, spec: str, cluster: str = "property_id") -> FitResult:
    d = prepare(df)
    cfg = SPECS[spec]
    X, names = design(d, cfg["terms"], cfg["fe"])
    beta, se, r2 = ols_cluster(d["log_rate"].to_numpy(), X, d[cluster].to_numpy())
    return FitResult(spec, names, beta, se, len(d), d[cluster].nunique(), X.shape[1], r2)


def results_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for spec, cfg in SPECS.items():
        res = fit(df, spec)
        for term in ("has_pool", "room_jacuzzi"):
            if term in cfg["terms"]:
                rows.append(res.row(term))
    return pd.DataFrame(rows)
