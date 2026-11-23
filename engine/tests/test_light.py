import numpy as np
import pandas as pd

from tcd.light import build_light, earnings_state, level_for, valuation_state


def test_levels_follow_documented_rule():
    assert level_for(0.10) == "green" and level_for(0.4999) == "green"
    assert level_for(0.50) == "yellow" and level_for(0.7999) == "yellow"
    assert level_for(0.80) == "red" and level_for(1.0) == "red"


def test_states():
    assert valuation_state(-1.0) == "below" and valuation_state(0.0) == "near" and valuation_state(1.0) == "above"
    assert valuation_state(None) == "unknown"
    assert earnings_state(-1.5) == "weakening" and earnings_state(0.2) == "flat" and earnings_state(1.0) == "growing"


def test_build_light_uses_partial_month():
    idx = pd.date_range("2026-09-30", periods=3, freq="ME")
    panel = pd.DataFrame({"risk_ret": [0.01, 0.02, -0.17], "pe_agg": [20, 19, 16.2], "val_z": [0.1, -0.6, -2.0],
                          "val_src": ["PE"] * 3, "earn_score": [0.5, 0.7, 0.27], "partial": [False, False, True]}, index=idx)
    cur = {"vol_hist_percentile": 0.97, "vol_1d_ann": 0.53, "vol_hist_median": 0.21, "vol_1d": 0.034,
           "var95_1d_simple_ret": 0.054, "date": "2026-11-20", "vol_hist_start": "1985-10-02"}
    L = build_light(cur, panel)
    assert L["level"] == "red" and L["mtd_month"] == "2026-11" and np.isclose(L["mtd_return"], -0.17)
    assert L["val_state"] == "below" and L["earn_state"] == "flat" and np.isclose(L["vol_ratio"], 0.53 / 0.21)
