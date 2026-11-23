import numpy as np
import pandas as pd

from tcd.signal_study import (block_bootstrap_spread, forward_excess, forward_max_drawdown,
                              newey_west, pit_buckets, verdict)


def _idx(n):
    return pd.date_range("2000-01-31", periods=n, freq="ME")


def test_forward_excess_uses_only_future_months():
    risk = pd.Series([0.0, 0.1, 0.2, 0.3], index=_idx(4))
    safe = pd.Series(0.0, index=risk.index)
    f = forward_excess(risk, safe, 2)
    assert np.isclose(f.iloc[0], np.log(1.1) + np.log(1.2))  # months t+1, t+2 only
    assert np.isnan(f.iloc[-1]) and np.isnan(f.iloc[-2])


def test_forward_max_drawdown():
    risk = pd.Series([0.0, 0.1, -0.5, 0.2, 0.0], index=_idx(5))
    dd = forward_max_drawdown(risk, 3)
    assert np.isclose(dd.iloc[0], -0.5)


def test_pit_buckets_ignore_future_values():
    rng = np.random.default_rng(0)
    s = pd.Series(rng.normal(size=200), index=_idx(200))
    b1 = pit_buckets(s, 5, 20)
    s2 = s.copy()
    s2.iloc[150:] += 100.0  # change only the future
    b2 = pit_buckets(s2, 5, 20)
    pd.testing.assert_series_equal(b1.iloc[:150], b2.iloc[:150])
    assert b1.iloc[:19].isna().all() and b1.iloc[19:].between(1, 5).all()


def test_newey_west_recovers_slope():
    rng = np.random.default_rng(1)
    x = rng.normal(size=2000)
    y = 0.5 * x + rng.normal(scale=0.5, size=2000)
    beta, t = newey_west(y, x, lag=5)
    assert abs(beta - 0.5 * x.std(ddof=1)) < 0.05 and t > 10


def test_bootstrap_spread_ci_contains_point():
    rng = np.random.default_rng(2)
    b = rng.integers(1, 6, 300)
    y = b * 0.01 + rng.normal(scale=0.01, size=300)
    point, lo, hi = block_bootstrap_spread(b, y, 5, reps=300)
    assert lo < point < hi and lo > 0


def test_verdict_directions():
    assert verdict(-0.2, -0.1, "return").startswith("supports")
    assert verdict(0.1, 0.2, "return").startswith("contradicts")
    assert verdict(-0.1, 0.2, "risk").startswith("inconclusive")
    assert verdict(0.05, 0.2, "risk").startswith("supports")


def test_verdict_low_side_flips():
    # Bottom bucket had more drawdowns (top-minus-bottom negative) -> supports low-side de-risking.
    assert verdict(-0.4, -0.1, "risk", "low").startswith("supports")
