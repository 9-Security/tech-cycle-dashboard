import json
import math

import numpy as np
import pandas as pd

from tcd.backtest import max_drawdown, metrics, simulate
from tcd.config import RegimeParams
from tcd.export import clean, regime_spans
from tcd.regime import classify_arrays, weights_for
from tcd.validation import deflated_sharpe, probabilistic_sharpe


def test_regime_priority():
    p = RegimeParams(vix_threshold=20, overheat_threshold=1.0, earn_threshold=-1.0)
    vix = np.array([25, 25, 10, 10, 10, np.nan])
    oh = np.array([2.0, 0.0, 2.0, 0.0, 0.0, np.nan])
    earn = np.array([-2, -2, -2, -2, 0, np.nan])
    assert classify_arrays(vix, oh, earn, p).tolist() == [2, 2, 1, 3, 4, 4]


def test_weights_lookup():
    p = RegimeParams(w_overheat=0.6, w_shock=0.1, w_digestion=0.5)
    assert weights_for(np.array([1, 2, 3, 4]), p).tolist() == [0.6, 0.1, 0.5, 1.0]


def test_simulate_costs_and_mix():
    risk = np.array([0.10, -0.10, 0.05])
    safe = np.array([0.01, 0.01, 0.01])
    sim = simulate(risk, safe, np.array([1.0, 0.0, 0.5]), cost_bps=10)
    assert math.isclose(sim.ret[0], 0.10)
    assert math.isclose(sim.ret[1], 0.01 - 0.001)
    assert math.isclose(sim.ret[2], 0.5 * 0.05 + 0.5 * 0.01 - 0.0005)


def test_max_drawdown():
    assert math.isclose(max_drawdown(np.array([1.0, 1.2, 0.6, 0.9])), -0.5)
    assert math.isclose(max_drawdown(np.array([0.8, 0.9])), -0.2)  # from initial capital 1.0


def test_metrics_basic():
    r = np.full(24, 0.01)
    m = metrics(r, np.zeros(24))
    assert math.isclose(m["cagr"], 1.01**12 - 1, rel_tol=1e-9)
    assert m["max_dd"] == 0.0


def test_dsr_penalises_many_trials():
    rng = np.random.default_rng(1)
    few = deflated_sharpe(0.15, rng.normal(0.05, 0.05, 5), 400, 0.0, 3.0)
    many = deflated_sharpe(0.15, rng.normal(0.05, 0.05, 5000), 400, 0.0, 3.0)
    assert many["sr0_monthly"] > few["sr0_monthly"]
    assert many["dsr"] < few["dsr"]
    assert 0.5 < probabilistic_sharpe(0.1, 0.0, 400, 0.0, 3.0) < 1.0


def test_clean_json_safe():
    out = clean({"a": float("nan"), "b": np.float64(1.5), "c": [np.inf, np.int64(2)]})
    assert json.dumps(out, allow_nan=False) == '{"a": null, "b": 1.5, "c": [null, 2]}'


def test_regime_spans():
    d = pd.date_range("2020-01-31", periods=5, freq="ME")
    spans = regime_spans(d, np.array([4, 4, 2, 2, 4]))
    assert [(s["regime"], s["start"], s["end"]) for s in spans] == [
        (4, "2020-01-31", "2020-02-29"), (2, "2020-03-31", "2020-04-30"), (4, "2020-05-31", "2020-05-31")]
