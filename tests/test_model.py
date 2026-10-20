import numpy as np
import statsmodels.api as sm

from hedonic.model import SPECS, design, fit, prepare
from hedonic.synthetic import TrueEffects, simulate_panel


def test_cluster_se_matches_statsmodels():
    df = prepare(simulate_panel(n_properties=30, n_stay_dates=8, seed=3))
    cfg = SPECS["between"]
    X, names = design(df, cfg["terms"], cfg["fe"])
    ours = fit(df, "between")
    ref = sm.OLS(df["log_rate"].to_numpy(), X).fit(
        cov_type="cluster", cov_kwds={"groups": df["property_id"].astype("category").cat.codes.to_numpy()})
    for term in ("has_pool", "room_jacuzzi"):
        i = names.index(term)
        assert np.isclose(ours.coef[i], ref.params[i], atol=1e-10)
        assert np.isclose(ours.se[i], ref.bse[i], rtol=1e-8)


def test_within_spec_cannot_estimate_property_level_pool():
    # Property fixed effects absorb any property-level amenity, so pool is excluded by design.
    assert "has_pool" not in SPECS["within"]["terms"]
    assert "property_id" in SPECS["within"]["fe"]


def test_recovers_true_premiums_on_average():
    truth = TrueEffects()
    pool, jac = [], []
    for seed in range(8):
        df = simulate_panel(n_properties=96, n_stay_dates=12, seed=seed)
        pool.append(fit(df, "between").row("has_pool")["coef_log"])
        jac.append(fit(df, "within").row("room_jacuzzi")["coef_log"])
    assert abs(np.mean(pool) - truth.pool) < 0.02
    assert abs(np.mean(jac) - truth.jacuzzi) < 0.01


def test_naive_pool_estimate_is_confounded_upward():
    df = simulate_panel()
    naive = fit(df, "naive").row("has_pool")["coef_log"]
    adjusted = fit(df, "between").row("has_pool")["coef_log"]
    assert naive > adjusted


def test_confidence_interval_contains_point_estimate():
    r = fit(simulate_panel(n_properties=40, n_stay_dates=8), "between").row("has_pool")
    assert r["ci_low_pct"] < r["premium_pct"] < r["ci_high_pct"]
    assert r["n_clusters"] == 40
