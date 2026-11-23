import json

import numpy as np
import pandas as pd
import pytest

from tcd.stocks import (StockConfig, analyze_stock, backtest, daily_frame, drop_stale_runs, load_watchlist,
                        market_stats, us_fundamentals, walk_forward_var)


def _px(n=3000, seed=0, sd=0.02, start="2010-01-04"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    vol = sd * np.exp(np.cumsum(rng.normal(0, 0.03, n)) * 0.3)  # time-varying vol
    p = 100 * np.exp(np.cumsum(rng.normal(0, 1, n) * vol))
    return pd.DataFrame({"close": p, "adjclose": p}, index=idx)


def test_watchlist_is_valid():
    wl = load_watchlist()
    assert len(wl["stocks"]) == 28 and set(wl["benchmarks"]) == {"US", "TW"}
    assert all(s.get("cik") for s in wl["stocks"] if s["market"] == "US")


def test_watchlist_validation_rejects_bad_entries(tmp_path):
    bad = {"benchmarks": {"US": "^NDX", "TW": "^TWII"},
           "stocks": [{"symbol": "X", "market": "US", "segment": "mega_cap", "name_en": "x", "name_zh": "x"}]}
    f = tmp_path / "w.json"
    f.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        load_watchlist(f)


def test_drop_stale_runs():
    r = pd.Series([0.01, 0, 0, 0, 0, 0, 0.02, 0, 0.01])
    out = drop_stale_runs(r, 5)
    assert len(out) == 4 and (out == 0).sum() == 1  # the 5-zero run is removed, a single zero kept


def test_taiwan_limit_filter_and_floor():
    px = _px(400)
    px.iloc[200:, :] *= 0.2  # unadjusted 5:1 corporate action -> -161% log jump
    df = daily_frame(px["adjclose"], 0.94, max_abs_logret=0.25)
    assert df["r"].abs().max() <= 0.25
    assert (df["rv_d"].dropna() >= 0.05 * df["rv_m"].dropna().reindex(df["rv_d"].dropna().index) - 1e-15).all()


def test_var_walk_forward_ignores_future_returns():
    px = _px(2500, seed=1)
    cfg = StockConfig()
    df = daily_frame(px["adjclose"], cfg.lam)
    fc1 = walk_forward_var(df, cfg)
    df2 = df.copy()
    late = df2.index >= pd.Timestamp("2016-01-01")
    df2.loc[late, ["y1", "y5", "r_next"]] *= 3.0
    fc2 = walk_forward_var(df2, cfg)
    pd.testing.assert_frame_equal(fc1.loc[:"2016-12-31"], fc2.loc[:"2016-12-31"])


def test_backtest_reports_coverage_on_well_specified_data():
    px = _px(3000, seed=2)
    cfg = StockConfig()
    df = daily_frame(px["adjclose"], cfg.lam)
    bt = backtest(df, walk_forward_var(df, cfg), cfg)
    assert bt["oos_days"] > 1000 and 0.03 < bt["breach_rate"] < 0.08


def test_market_stats_beta():
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2024-01-01", periods=400)
    b = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 400)))
    bench = pd.Series(b, index=idx)
    stock = pd.Series(100 * np.cumprod(1 + 1.5 * bench.pct_change().fillna(0) + rng.normal(0, 0.002, 400)), index=idx)
    m = market_stats(stock, bench)
    assert abs(m["beta_1y"] - 1.5) < 0.1 and m["from_52w_high"] <= 0


def test_growth_not_meaningful_for_tiny_base():
    q = lambda vals, ends, filed: pd.DataFrame({"start": pd.to_datetime(ends) - pd.Timedelta(days=89), "end": pd.to_datetime(ends),
                                                "val": vals, "filed": pd.to_datetime(filed), "form": "10-Q", "tag": "T", "priority": 0})
    ends = pd.date_range("2023-03-31", "2026-09-30", freq="QE")
    filed = ends + pd.Timedelta(days=30)
    facts = {"revenue": q([100.0] * len(ends), ends, filed),
             # tiny earnings through 2025-09 (the year-ago TTM window), normal afterwards
             "net_income": q([0.01 if e <= pd.Timestamp("2025-09-30") else 5.0 for e in ends], ends, filed),
             "capex": q([10.0] * len(ends), ends, filed)}
    shares = pd.DataFrame({"end": ends, "val": 10.0, "filed": filed, "priority": 0})
    f = us_fundamentals(facts, shares, pd.Series(dtype=float, index=pd.DatetimeIndex([])),
                        pd.Series([50.0], index=[pd.Timestamp("2026-11-20")]), pd.Timestamp("2026-11-20"))
    assert f["net_income_growth"] is None  # base ~0 -> not meaningful
    assert f["revenue_growth"] == pytest.approx(0.0) and f["capex_to_revenue"] == pytest.approx(0.1)


def test_analyze_stock_shape():
    px = _px(2500, seed=4)
    spec = {"symbol": "T.TW", "market": "TW", "segment": "foundry", "name_en": "t", "name_zh": "t"}
    row = analyze_stock(spec, px, px["adjclose"], StockConfig())
    assert row["level"] in {"green", "yellow", "red"} and len(row["chart"]["dates"]) == 252
    assert row["fundamentals"] is None and 0 < row["var95"] < 0.5
