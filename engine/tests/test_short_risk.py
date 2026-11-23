import pytest
import numpy as np
import pandas as pd

from tcd.short_risk import (ShortRiskConfig, christoffersen, daily_frame, diebold_mariano, fit_var,
                            kupiec, qlike, walk_forward)


def test_kupiec_and_christoffersen():
    b = np.zeros(1000, bool)
    b[::20] = True  # exactly 5%, evenly spaced
    k = kupiec(b, 0.05)
    assert k["breaches"] == 50 and k["p_value"] > 0.99
    assert kupiec(np.r_[np.ones(100, bool), np.zeros(900, bool)], 0.05)["p_value"] < 1e-6
    clustered = np.zeros(1000, bool)
    clustered[100:150] = True
    assert christoffersen(clustered)["p_value"] < 1e-6
    iid = np.random.default_rng(3).uniform(size=5000) < 0.05  # independent breaches
    assert christoffersen(iid)["p_value"] > 0.05


def test_qlike_prefers_truth_and_dm_sign():
    rng = np.random.default_rng(0)
    true_var = np.exp(rng.normal(-9, 0.5, 4000))
    y = true_var * rng.chisquare(1, 4000)
    good, bad = qlike(y, true_var), qlike(y, np.full(4000, true_var.mean()))
    assert good.mean() < bad.mean()
    assert diebold_mariano(bad, good, 5) > 2  # positive => second (good) is better


def test_log_model_always_positive():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(500, 2))
    y = np.exp(-9 + 0.5 * X[:, 0] + rng.normal(0, 0.3, 500))
    m = fit_var(X, y, ["a", "b"], "log", 1e-12)
    assert (m.predict(rng.normal(0, 10, size=(100, 2)), 1e-12) > 0).all()


def test_epu_is_lagged_one_day(raw):
    raw.fred["epu"] = pd.Series(np.arange(len(pd.date_range("1985-01-01", "2026-11-20"))) + 1.0,
                                index=pd.date_range("1985-01-01", "2026-11-20"))
    df = daily_frame(raw, ShortRiskConfig(epu_window=1))
    d = pd.Timestamp("2010-06-15")
    expected = raw.fred["epu"].loc[d - pd.Timedelta(days=1)]
    assert np.isclose(np.exp(df.loc[d, "epu"]), expected)
    del raw.fred["epu"]


def test_walk_forward_ignores_future_returns(raw):
    cfg = ShortRiskConfig(oos_start_year=2005, horizons=(1,))
    df = daily_frame(raw, cfg)
    fc1, _ = walk_forward(df, cfg)
    df2 = df.copy()
    late = df2.index >= pd.Timestamp("2008-01-01")
    df2.loc[late, ["y1", "r_next"]] *= 5.0  # change only targets realized in 2008+
    fc2, _ = walk_forward(df2, cfg)
    cols = ["har_vix_1", "q_har_vix"]
    pd.testing.assert_frame_equal(fc1.loc[:"2008-12-31", cols], fc2.loc[:"2008-12-31", cols])


def test_oos_quantile_uses_only_known_oos_residuals():
    import numpy as np
    import pandas as pd
    from tcd.short_risk import ShortRiskConfig, oos_quantile
    cfg = ShortRiskConfig(min_oos_resid=50)
    n = 400
    rng = np.random.default_rng(1)
    r = rng.normal(0, 0.02, n)
    out = pd.DataFrame({"har_1": np.full(n, 0.01 ** 2)})  # forecast vol half the true vol
    out.loc[:99, "har_1"] = np.nan                         # no OOS forecast yet (burn-in)
    known = np.zeros(n, bool)
    known[:300] = True
    q = oos_quantile(out, "har", r, known, cfg)
    want = np.quantile(r[100:300] / 0.01, 0.05)
    assert q == pytest.approx(want)
    assert q < -3.0  # under-forecast variance -> wider quantile, which is the point of the fix
    known[:] = False
    known[:120] = True
    assert np.isnan(oos_quantile(out, "har", r, known, cfg))  # only 20 OOS residuals known
