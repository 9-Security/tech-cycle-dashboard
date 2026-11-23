import numpy as np
import pandas as pd

from tcd.config import EngineConfig, TiltGrid
from tcd.cross_market import CRITERIA, MARKETS, Market, evaluate_market, market_panel, pooled_bootstrap, verdict
from tcd.features import build_panel


def test_criteria_are_pre_registered():
    assert CRITERIA["C1_min_markets_sharpe"] == 6 and CRITERIA["C3_min_markets_mdd"] == 6
    assert CRITERIA["C2_ci_level"] == 0.90 and len(MARKETS) == 9


def test_market_panel_is_future_invariant(raw):
    cfg = EngineConfig()
    tech = build_panel(raw, cfg.features)
    px = raw.prices["C1"].to_frame("adjclose").assign(close=lambda d: d["adjclose"])
    vix, tb = raw.vix, raw.fred["tbill_3m"]
    full = market_panel(px, vix, tb, None, cfg.features, pd.Timestamp("2026-10-31"))
    cut = pd.Timestamp("2018-03-02")
    part = market_panel(px[px.index <= cut], vix[vix.index <= cut], tb[tb.index <= cut], None, cfg.features, pd.Timestamp("2018-02-28"))
    cols = ["risk_ret", "safe_ret", "val_z_proxy", "rv21", "rv63", "vol_vix"]
    pd.testing.assert_frame_equal(full.loc[part.index, cols], part[cols], rtol=1e-12, atol=1e-12)
    assert full["val_z_pe"].isna().all()  # non-tech markets get no tech fundamentals


def test_evaluate_and_verdict(raw):
    cfg = EngineConfig()
    px = raw.prices["C0"].to_frame("adjclose").assign(close=lambda d: d["adjclose"])
    panel = market_panel(px, raw.vix, raw.fred["tbill_3m"], None, cfg.features, pd.Timestamp("2026-10-31"))
    small = TiltGrid(c_px=(0.0, 0.25), c_pe=(0.0,), c_capex=(0.0,), base=(1.0,), earn=((1.0, -1.0),),
                     vol=(("rv63", float("inf")), ("rv21", 0.2)))
    r = evaluate_market(Market("C0", "synthetic", False), panel, small, cfg.backtest)
    assert r.row["months"] > 60 and len(r.v3_ret) == len(r.bh_ret) == r.row["months"]
    pooled = pooled_bootstrap([r, r], 12, 200, 0.9)
    assert pooled["ci"][0] <= pooled["mean_sharpe_diff"] <= pooled["ci"][1]
    v = verdict([r.row] * 9, pooled)
    assert set(v) >= {"C1", "C2", "C3", "overall_pass"}
