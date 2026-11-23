from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from tcd import ledger as L


def _row(sym="A", market="US", d="2024-01-02", var95=0.03, hv=1e-4, stale=False):
    return {"symbol": sym, "market": market, "last_date": d, "var95": var95, "har_var": hv, "ewma_var": hv * 1.1,
            "vol_1d_ann": 0.2, "level": "green", "stale": stale}


def test_bar_is_final_respects_local_close():
    # 2024-01-02 is a Tuesday. 06:00 UTC = 14:00 Taipei (before the 14:30 cutoff).
    assert not L.bar_is_final("TW", "2024-01-02", datetime(2024, 1, 2, 6, 0, tzinfo=timezone.utc))
    assert L.bar_is_final("TW", "2024-01-02", datetime(2024, 1, 2, 7, 7, tzinfo=timezone.utc))
    # 20:00 UTC = 15:00 New York (EST) -> intraday; 22:15 UTC -> final.
    assert not L.bar_is_final("US", "2024-01-02", datetime(2024, 1, 2, 20, 0, tzinfo=timezone.utc))
    assert L.bar_is_final("US", "2024-01-02", datetime(2024, 1, 2, 22, 15, tzinfo=timezone.utc))
    assert L.bar_is_final("US", "2024-01-01", datetime(2024, 1, 2, 1, 0, tzinfo=timezone.utc))


def test_ledger_is_append_only_and_first_write_wins(tmp_path):
    p = tmp_path / "ledger.csv"
    now = datetime(2024, 1, 3, tzinfo=timezone.utc)
    r1 = L.forecast_rows([_row(var95=0.03), _row("B", stale=True)], "t1", now, "x", "m1")
    assert [r["symbol"] for r in r1] == ["A"]  # stale rows are not forecasts
    assert L.append_ledger(p, r1) == 1
    before = p.read_bytes()
    r2 = L.forecast_rows([_row(var95=0.99), _row("C")], "t2", now, "x", "m1")
    assert L.append_ledger(p, r2) == 1  # A already logged: kept as first written
    after = p.read_bytes()
    assert after.startswith(before)
    led = L.read_ledger(p)
    assert led.set_index("symbol").loc["A", "var95"] == pytest.approx(0.03)
    assert L.append_ledger(p, r2) == 0 and p.read_bytes() == after


def test_ledger_rejects_tampered_header(tmp_path):
    p = tmp_path / "ledger.csv"
    p.write_text("foo,bar\n1,2\n")
    with pytest.raises(ValueError):
        L.append_ledger(p, [dict(zip(L.LEDGER_COLUMNS, ["2024-01-02", "A"] + [""] * 9))])


def _px(values, start="2024-01-02"):
    idx = pd.bdate_range(start, periods=len(values))
    s = pd.Series(values, index=idx, dtype=float)
    return pd.DataFrame({"close": s, "adjclose": s})


def test_evaluate_statuses_and_breach():
    led = pd.DataFrame([
        {"origin_date": "2024-01-02", "symbol": "A", "market": "US", "var95": 0.03, "har_var": 1e-4, "ewma_var": 1e-4, "level": "green", "model_id": "m"},
        {"origin_date": "2024-01-03", "symbol": "A", "market": "US", "var95": 0.03, "har_var": 1e-4, "ewma_var": 1e-4, "level": "green", "model_id": "m"},
        {"origin_date": "2024-01-04", "symbol": "A", "market": "US", "var95": 0.03, "har_var": 1e-4, "ewma_var": 1e-4, "level": "green", "model_id": "m"},
        {"origin_date": "2024-01-02", "symbol": "T", "market": "TW", "var95": 0.03, "har_var": 1e-4, "ewma_var": 1e-4, "level": "red", "model_id": "m"},
    ])
    prices = {"A": _px([100, 96, 97]), "T": _px([100, 20])}  # A: -4% then +1%; T: -80% (data error)
    out = L.evaluate(led, prices, ("US", "TW"), L.ReviewConfig()).set_index(["symbol", "origin_date"])
    assert out.loc[("A", "2024-01-02"), "status"] == "scored" and out.loc[("A", "2024-01-02"), "breach"] is True
    assert out.loc[("A", "2024-01-03"), "breach"] is False
    assert out.loc[("A", "2024-01-04"), "status"] == "pending"
    assert out.loc[("T", "2024-01-02"), "status"] == "data_error"


def test_summary_gates_and_detects_miscalibration():
    rng = np.random.default_rng(0)
    rows = []
    dates = pd.bdate_range("2024-01-02", periods=300)
    for sym in ["A", "B", "C"]:
        for d in dates:
            r = rng.normal(0, 0.02)
            for model, sd in (("good", 0.02), ("bad", 0.01)):
                v = 1 - np.exp(-1.6449 * sd)
                rows.append({"model": model, "origin_date": str(d.date()), "target_date": str(d.date()), "symbol": sym,
                             "market": "US", "status": "scored", "ret": r, "var95": v, "breach": bool(np.expm1(r) < -v),
                             "har_var": sd ** 2, "ewma_var": 0.02 ** 2, "level": "green",
                             "qlike_har": np.log(sd ** 2) + r * r / sd ** 2, "qlike_ewma": np.log(4e-4) + r * r / 4e-4,
                             "var_ratio": r * r / sd ** 2, "model_id": "m"})
    df = pd.DataFrame(rows)
    cfg = L.ReviewConfig()
    for model, want in (("good", "consistent"), ("bad", "too_many")):
        oc = df[df["model"] == model].drop(columns="model")
        led = oc[["origin_date", "symbol", "market", "model_id"]]
        rv = L.summarize(oc, led, [], cfg, "t")
        assert rv["markets"]["US"]["verdict"] == want, model
        assert rv["stocks"]["A"]["verdict"] != "insufficient"
    short = df[(df["model"] == "good") & (df["target_date"] < "2024-02-15")].drop(columns="model")
    rv = L.summarize(short, short[["origin_date", "symbol", "market", "model_id"]], [], cfg, "t")
    assert rv["markets"]["US"]["verdict"] == "insufficient" and rv["stocks"]["A"]["verdict"] == "insufficient"


def test_update_end_to_end(tmp_path):
    from tcd.stocks import StockConfig
    rows = [_row(d="2024-01-02")]
    now = datetime(2024, 1, 3, tzinfo=timezone.utc)
    rv = L.update(tmp_path, rows, {"A": _px([100, 101])}, ("US",), "t", now, "x", StockConfig())
    assert rv["last_run"]["forecasts_added"] == 1
    assert (tmp_path / "forecasts" / "stocks_outcomes.csv").exists() and (tmp_path / "forecast_review.json").exists()
    assert rv["markets"]["US"]["n"] == 1 and rv["markets"]["US"]["verdict"] == "insufficient"
