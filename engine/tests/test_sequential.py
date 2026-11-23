import numpy as np
import pandas as pd

from tcd import sequential as S, var_panel as P


def test_registered_schedule_and_critical_counts():
    assert S.LOOKS == (60, 120, 250) and S.ALPHAS == (0.01, 0.015, 0.025) and abs(sum(S.ALPHAS) - 0.05) < 1e-12
    assert [S.binom_critical(n, a) for n, a in zip(S.LOOKS, S.ALPHAS)] == [8, 13, 21]


def test_single_series_looks():
    b = np.zeros(130, bool)
    assert S.single_series(b[:59])["verdict"] == "before_first_look"
    assert S.single_series(b)["verdict"] == "not_rejected_at_120" and S.single_series(b)["next_look"] == 250
    b[:8] = True  # 8 breaches in the first 60 days
    r = S.single_series(b)
    assert r["verdict"] == "too_many_at_60" and r["looks"][0]["warning"]


def test_pooled_looks():
    rng = np.random.default_rng(0)
    dates = np.repeat(np.arange(130), 10)
    calm = (rng.random(1300) < 0.03).astype(float)
    assert S.pooled(calm, dates)["verdict"] == "not_rejected_at_120"
    hot = (rng.random(1300) < 0.15).astype(float)
    assert S.pooled(hot, dates)["verdict"] == "too_many_at_60"


def test_panel_forecast_uses_only_past_data():
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2000-01-03", periods=2600)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(idx)))), index=idx)
    a = P.forecast(close)
    assert a is not None and 0 < a["var95"] < 0.1 and a["date"] == str(idx[-1].date())
    # Future data must not change the walk-forward forecasts of earlier years.
    f_short = P.walk_forward(P.frame(close.iloc[:2000]))
    f_full = P.walk_forward(P.frame(close))
    common = f_short.dropna().index
    common = common[common.year < close.index[1999].year]
    assert len(common) > 0 and np.allclose(f_short[common], f_full[common])
