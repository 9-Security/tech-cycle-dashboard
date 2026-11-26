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
    for model, want in (("good", "not_rejected"), ("bad", "too_many")):
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
    now = datetime(2024, 1, 4, tzinfo=timezone.utc)   # after the 01-03 target bar closed
    rv = L.update(tmp_path, rows, {"A": _px([100, 101]), "^NDX": _px([10, 11])}, ("US",), "t", now, "x", StockConfig())
    assert rv["last_run"]["forecasts_added"] == 1
    assert (tmp_path / "forecasts" / "stocks_outcomes.csv").exists() and (tmp_path / "forecast_review.json").exists()
    assert rv["markets"]["US"]["n"] == 1 and rv["markets"]["US"]["verdict"] == "insufficient"


def test_non_trading_bars_are_skipped(tmp_path):
    import json
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    nt = {"T": {"2024-01-03"}}
    assert L.forecast_rows([_row("T", "TW", d="2024-01-03")], "t", now, "x", "m", nt) == []
    led = pd.DataFrame([{"origin_date": "2024-01-02", "symbol": "T", "market": "TW", "var95": 0.03, "har_var": 1e-4,
                         "ewma_var": 1e-4, "level": "green", "model_id": "m"}])
    px = _px([100, 100, 95])  # 01-03 is a carried-forward holiday bar; real next bar is 01-04 (-5%)
    out = L.evaluate(led, {"T": px}, ("TW",), L.ReviewConfig(), nt).iloc[0]
    assert out["target_date"] == "2024-01-04" and bool(out["breach"])
    (tmp_path / "official_check.json").write_text(json.dumps({"stocks": {"T": {"extra": ["2024-01-03"]}, "U": {"extra": []}}}))
    assert L.non_trading_days(tmp_path / "official_check.json") == {"T": {"2024-01-03"}}


# ---------------------------------------------------------- review round 3
def test_origin_must_be_a_benchmark_trading_day_and_model_date_must_match():
    now = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
    od = {"TW": {"2026-10-22"}, "US": {"2026-10-22"}}
    holiday = _row("T", "TW", d="2026-10-23")              # Yahoo bar on a closure, ^TWII ends 10-22
    halted = {**_row("H", "US", d="2026-10-22"), "model_last_date": "2026-10-12"}
    ok = {**_row("U", "US", d="2026-10-22"), "model_last_date": "2026-10-22"}
    rows = L.forecast_rows([holiday, halted, ok], "t", now, "x", "m", None, od)
    assert [r["symbol"] for r in rows] == ["U"]


def test_target_skips_days_the_benchmark_did_not_trade():
    led = pd.DataFrame([{"origin_date": "2024-01-02", "symbol": "A", "market": "US", "var95": 0.03,
                         "har_var": 1e-4, "ewma_var": 1e-4, "level": "green", "model_id": "m"}])
    px = _px([100, 100, 95])  # 01-03 carried forward; the benchmark has no bar that day
    od = {"US": {"2024-01-02", "2024-01-04"}, "TW": None}
    out = L.evaluate(led, {"A": px}, ("US",), L.ReviewConfig(), None, od).iloc[0]
    assert out["target_date"] == "2024-01-04" and bool(out["breach"])


def test_final_outcomes_survive_a_failed_fetch_and_model_id_stays_text(tmp_path):
    from tcd.stocks import StockConfig
    mid = "012345678901"  # all digits: must not become a number on read-back
    p = tmp_path / "forecasts" / "stocks_ledger.csv"
    p.parent.mkdir(parents=True)
    L.append_ledger(p, [{"origin_date": "2024-01-02", "symbol": "A", "market": "US", "issued_at": "t",
                         "var95": "0.03", "har_var": "1e-4", "ewma_var": "1e-4", "vol_1d_ann": "0.2",
                         "level": "green", "engine_version": "x", "model_id": mid}])
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    L.update(tmp_path, [], {"A": _px([100, 96]), "^NDX": _px([10, 11])}, ("US",), "t1", now, "x", StockConfig())
    L.update(tmp_path, [], {}, ("TW",), "t2", now, "x", StockConfig())      # other market: rewrite path
    L.update(tmp_path, [], {}, ("US",), "t3", now, "x", StockConfig())      # A's prices missing now
    oc = L.read_outcomes(tmp_path / "forecasts" / "stocks_outcomes.csv")
    row = oc.iloc[0]
    assert row["status"] == "scored" and row["model_id"] == mid and row["target_date"] == "2024-01-03"


def test_verdicts_use_only_the_current_model_with_aliases():
    oc = pd.DataFrame([
        {"origin_date": "2024-01-02", "target_date": "2024-01-03", "symbol": "A", "market": "US", "status": "scored",
         "ret": -0.05, "var95": 0.03, "breach": True, "har_var": 1e-4, "ewma_var": 1e-4, "level": "green",
         "qlike_har": 0.0, "qlike_ewma": 0.0, "var_ratio": 25.0, "model_id": "old"},
        {"origin_date": "2024-01-02", "target_date": "2024-01-03", "symbol": "B", "market": "US", "status": "scored",
         "ret": 0.0, "var95": 0.03, "breach": False, "har_var": 1e-4, "ewma_var": 1e-4, "level": "green",
         "qlike_har": 0.0, "qlike_ewma": 0.0, "var_ratio": 0.0, "model_id": "alias_of_new"},
    ])
    led = oc[["origin_date", "symbol", "market", "model_id"]]
    L.MODEL_ID_ALIASES["alias_of_new"] = "new"
    try:
        rv = L.summarize(oc, led, [], L.ReviewConfig(), "t", "new")
    finally:
        del L.MODEL_ID_ALIASES["alias_of_new"]
    assert rv["markets"]["US"]["n"] == 1 and rv["markets"]["US"]["breaches"] == 0
    assert rv["other_models"] == {"old": 1}


def test_ci_accounts_for_breaches_clustering_over_days():
    # 20 names x 120 days; breaches come in 5-day bursts hitting all names.
    dates = np.repeat(np.arange(120), 20)
    day_hit = np.zeros(120, bool)
    for s in range(0, 120, 20):
        day_hit[s:s + 5] = True
    x = np.repeat(day_hit, 20).astype(float) * 0.2
    m, lo0, hi0 = L._clustered_rate(x, dates, 1.6449, lag=0)
    m, lo5, hi5 = L._clustered_rate(x, dates, 1.6449, lag=5)
    assert (hi5 - lo5) > 1.5 * (hi0 - lo0)


def test_model_id_guard():
    """Changing how a stock forecast is made changes model_id, and the live record
    restarts from zero for the new model. If this fails, that is intended only
    with a documented model change (methodology section 14); update the expected
    id here, and never add an alias unless the forecasting code is byte-identical."""
    from tcd.stocks import StockConfig
    assert L.model_id(StockConfig()) == "efb69ecbf292"
    assert L.MODEL_ID_ALIASES == {}



def test_partial_target_bar_is_not_scored_and_stays_pending():
    led = pd.DataFrame([{"origin_date": "2024-01-02", "symbol": "A", "market": "US", "var95": 0.03,
                         "har_var": 1e-4, "ewma_var": 1e-4, "level": "green", "model_id": "m"}])
    px = _px([100, 90])  # 2024-01-03 bar, seen during the session
    during = datetime(2024, 1, 3, 18, 0, tzinfo=timezone.utc)   # 13:00 New York
    after = datetime(2024, 1, 3, 22, 15, tzinfo=timezone.utc)
    od = {"US": {"2024-01-02", "2024-01-03"}, "TW": None}
    assert L.evaluate(led, {"A": px}, ("US",), L.ReviewConfig(), None, od, None, during).iloc[0]["status"] == "pending"
    assert L.evaluate(led, {"A": px}, ("US",), L.ReviewConfig(), None, od, None, after).iloc[0]["status"] == "scored"
    od_missing = {"US": None, "TW": None}   # benchmark fetch failed: never score
    assert L.evaluate(led, {"A": px}, ("US",), L.ReviewConfig(), None, od_missing, None, after).iloc[0]["status"] == "pending"


def test_frozen_rows_are_rewritten_byte_identical(tmp_path):
    p = tmp_path / "o.csv"
    row = {c: None for c in L.OUTCOME_COLUMNS}
    row.update(origin_date="2024-01-02", symbol="A", market="US", status="scored", ret=0.006911683841295721)
    fresh = pd.DataFrame([row], columns=L.OUTCOME_COLUMNS)
    L.merge_outcomes(p, fresh, ("US",))
    before = p.read_bytes()
    L.merge_outcomes(p, pd.DataFrame(columns=L.OUTCOME_COLUMNS), ("US",))
    assert p.read_bytes() == before


def test_session_guard():
    import pandas as pd
    from tcd.cli import session_in_progress
    d = pd.Timestamp("2024-01-03")
    assert session_in_progress("US", d, datetime(2024, 1, 3, 15, 0, tzinfo=timezone.utc))       # 10:00 New York
    assert not session_in_progress("US", d, datetime(2024, 1, 3, 22, 15, tzinfo=timezone.utc))  # after the close
    assert session_in_progress("TW", d, datetime(2024, 1, 3, 2, 0, tzinfo=timezone.utc))        # 10:00 Taipei
    assert not session_in_progress("TW", d, datetime(2024, 1, 3, 7, 7, tzinfo=timezone.utc))    # 15:07 Taipei
