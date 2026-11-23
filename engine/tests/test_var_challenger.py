import numpy as np
import pandas as pd

from tcd import var_challenger as V


def _frames(n=1200, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2000-01-03", periods=n)
    r = pd.Series(rng.normal(0, 0.01, n), index=idx)
    df = pd.DataFrame({"r_next": r.shift(-1)})
    fc = pd.DataFrame({"har_vix_1": np.full(n, 1e-4)}, index=idx)
    fc.loc[idx[:100], "har_vix_1"] = np.nan  # burn-in without OOS forecasts
    fc["q_har_vix"] = -1.645
    return df, fc


def test_quantile_uses_only_outcomes_known_before_the_forecast():
    df, fc = _frames()
    q = V.rolling_quantile(df, fc, "har_vix", window=200)
    t = df.index[700]
    # Changing outcomes from day t onwards must not change the quantile used at t.
    df2 = df.copy()
    df2.loc[t:, "r_next"] = -0.5
    q2 = V.rolling_quantile(df2, fc, "har_vix", window=200)
    assert q.loc[t] == q2.loc[t]
    assert q2.loc[df.index[702]] != q.loc[df.index[702]]  # z_{t} becomes known at t+1
    assert q.iloc[:300].isna().all() and q.notna().iloc[350]  # needs `window` OOS residuals


def test_registered_decision_rule():
    ok = {"n": 300, "kupiec_p": 0.5, "christoffersen_p": 0.5}
    bad = {"n": 300, "kupiec_p": 0.01, "christoffersen_p": 0.5}
    assert V.live_decision(ok, bad) == "recommend_switch"
    assert V.live_decision(ok, ok) == "keep_incumbent"
    assert V.live_decision(bad, bad) == "keep_incumbent"
    assert V.live_decision({**ok, "n": 100}, bad) == "insufficient"
    assert V.WINDOW == 500  # registered value: changing it is a new challenger
