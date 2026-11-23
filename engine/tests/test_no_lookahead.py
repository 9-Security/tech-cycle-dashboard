"""Future-invariance: truncating the data after date D must not change any
signal, target or walk-forward choice for months that ended before D."""

import numpy as np
import pandas as pd
import pytest
from conftest import truncate

from tcd.config import EngineConfig, ParamGrid, RegimeParams
from tcd.features import build_panel
from tcd.validation import nested_walk_forward, prepare, run, run_grid

CFG = EngineConfig()
SIGNALS = ["risk_ret", "safe_ret", "vix", "pe_agg", "val_z", "capex_z", "earn_score", "overheat_score"]


@pytest.fixture(scope="module")
def full_panel(raw):
    return build_panel(raw, CFG.features)


@pytest.mark.parametrize("cutoff", ["2008-06-17", "2015-02-10", "2018-03-02", "2021-09-03"])
def test_panel_is_future_invariant(raw, full_panel, cutoff):
    cut = build_panel(truncate(raw, cutoff), CFG.features)
    complete = cut[~cut["partial"]]
    assert len(complete) > 100
    a = full_panel.loc[complete.index, SIGNALS]
    b = complete[SIGNALS]
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=1e-12, atol=1e-12)


def test_partial_month_is_flagged(raw):
    p = build_panel(truncate(raw, "2021-09-03"), CFG.features)
    assert bool(p["partial"].iloc[-1]) and p.index[-1] == pd.Timestamp("2021-09-30")
    assert not p["partial"].iloc[:-1].any()


def test_lag1_execution(full_panel):
    bt = prepare(full_panel, CFG.backtest)
    codes, target, sim = run(bt, RegimeParams(), CFG.backtest.cost_bps)
    assert np.allclose(sim.executed[1:], target[:-1])
    assert sim.cost[0] == 0.0


def test_walk_forward_choice_ignores_test_year_returns(full_panel):
    grid = ParamGrid(vix_threshold=(18.0, 30.0), overheat_threshold=(1.0, 2.0), earn_threshold=(-1.0,),
                     w_overheat=(0.5,), w_shock=(0.0, 0.5), w_digestion=(0.5,))
    bt = prepare(full_panel, CFG.backtest)
    params = list(grid)
    wf1 = nested_walk_forward(bt, run_grid(bt, params, 15.0), CFG.backtest, 2010)

    # Scramble every return from 2005 onward: folds up to 2005 must not change.
    bt.risk = bt.risk.copy()
    mask = bt.dates >= pd.Timestamp("2005-01-01")
    bt.risk[mask] = np.random.default_rng(0).normal(0, 0.2, mask.sum())
    wf2 = nested_walk_forward(bt, run_grid(bt, params, 15.0), CFG.backtest, 2010)
    for f1, f2 in zip(wf1.folds, wf2.folds):
        if f1["test_year"] <= 2005:
            assert f1["params"] == f2["params"], f1["test_year"]


def test_pe_valuation_is_used_once_available(full_panel):
    src = full_panel["val_src"]
    first_pe = src[src == "PE"].index.min()
    assert first_pe is not None and (src[src.index >= first_pe] == "PE").all()
    assert src[src.index < first_pe].isin(["PX", "NA"]).all()
