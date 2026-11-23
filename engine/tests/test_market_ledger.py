from datetime import datetime, timezone

import numpy as np
import pandas as pd

from tcd import market_ledger as M

SHORT = {"date": "2024-01-02", "model": "har_vix", "var95_1d_simple_ret": 0.03, "vol_1d": 0.01, "vol_5d": 0.0224,
         "ewma_vol_ann": 0.18}
VOL = {"month_end": {"date": "2023-12-31", "vol": 0.20, "band90": [0.12, 0.33]},
       "provisional": {"date": "2024-01-31", "vol": 0.25, "band90": [0.15, 0.40]}}


def test_rows_only_final_bars_and_complete_months():
    after = datetime(2024, 1, 2, 22, 15, tzinfo=timezone.utc)
    during = datetime(2024, 1, 2, 18, 0, tzinfo=timezone.utc)
    rows = M.forecast_rows(SHORT, VOL, "red", "t", after, "x")
    assert [(r["target"], r["origin_date"]) for r in rows] == [("var_1d", "2024-01-02"), ("vol_5d", "2024-01-02"),
                                                               ("vol_1m", "2023-12-31")]
    assert [r["target"] for r in M.forecast_rows(SHORT, VOL, "red", "t", during, "x")] == ["vol_1m"]
    assert rows[0]["level"] == "red" and abs(float(rows[1]["har_var"]) - 0.0224 ** 2 / 5) < 1e-12


def _ledger(tmp_path):
    p = tmp_path / "forecasts" / "market_ledger.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = M.forecast_rows(SHORT, VOL, "red", "t", datetime(2024, 1, 3, tzinfo=timezone.utc), "x")
    M.append_ledger(p, rows, M.COLUMNS, ("target", "origin_date"))
    return M._read(p, M.COLUMNS)


def test_scoring_each_target(tmp_path):
    led = _ledger(tmp_path)
    days = pd.bdate_range("2024-01-02", periods=7)
    r = pd.Series([0.0, -0.05, 0.01, 0.01, 0.01, 0.01, 0.0], index=days)  # day 1 after origin: -5%
    panel = pd.DataFrame({"rv21": [0.2, 0.26], "partial": [False, False]},
                         index=pd.to_datetime(["2023-12-31", "2024-01-31"]))
    oc = M.evaluate(led, r, panel, set()).set_index("target")
    assert oc.loc["var_1d", "status"] == "scored" and bool(oc.loc["var_1d", "breach"])
    assert oc.loc["vol_5d", "target_end"] == str(days[5].date())
    assert abs(oc.loc["vol_5d", "realized"] - np.mean(np.square([-0.05, 0.01, 0.01, 0.01, 0.01]))) < 1e-12
    assert oc.loc["vol_1m", "status"] == "scored" and bool(oc.loc["vol_1m", "in_band"])
    assert abs(oc.loc["vol_1m", "log_error"] - np.log(0.26 / 0.20)) < 1e-12


def test_pending_until_data_and_partial_month_not_used(tmp_path):
    led = _ledger(tmp_path)
    r = pd.Series([0.0, 0.01], index=pd.bdate_range("2024-01-02", periods=2))
    panel = pd.DataFrame({"rv21": [0.2, 0.26], "partial": [False, True]},
                         index=pd.to_datetime(["2023-12-31", "2024-01-31"]))
    oc = M.evaluate(led, r, panel, set()).set_index("target")
    assert oc.loc["var_1d", "status"] == "scored"
    assert oc.loc["vol_5d", "status"] == "pending" and oc.loc["vol_1m", "status"] == "pending"


def test_var_verdict_gate():
    s = pd.DataFrame({"origin_date": [f"d{i:04d}" for i in range(300)], "breach": [i % 20 == 0 for i in range(300)],
                      "ratio": 1.0, "qlike_har": 0.0, "qlike_ewma": 0.0, "realized": 1e-4, "har_var": 1e-4,
                      "level": "green"})
    cfg = M.MarketReviewConfig()
    assert M._summ_var(s.iloc[:200], cfg)["verdict"] == "insufficient"
    assert M._summ_var(s, cfg)["verdict"] == "consistent"


def test_challenger_row_logged_with_its_own_model_id():
    after = datetime(2024, 1, 2, 22, 15, tzinfo=timezone.utc)
    ch = {"current": {"var95_1d_simple_ret": 0.035}}
    rows = M.forecast_rows(SHORT, VOL, "red", "t", after, "x", ch)
    by = {r["target"]: r for r in rows}
    assert float(by["var_1d_challenger"]["var95"]) == 0.035
    assert by["var_1d_challenger"]["model_id"] != by["var_1d"]["model_id"]


def test_partial_bars_and_months_are_never_scored(tmp_path):
    led = _ledger(tmp_path)
    days = pd.bdate_range("2024-01-02", periods=7)
    r = pd.Series([0.0, -0.05, 0.01, 0.01, 0.01, 0.01, 0.0], index=days)
    panel = pd.DataFrame({"rv21": [0.2, 0.26], "partial": [False, False]},
                         index=pd.to_datetime(["2023-12-31", "2024-01-31"]))
    during = datetime(2024, 1, 3, 18, 0, tzinfo=timezone.utc)        # 2024-01-03 still trading
    oc = M.evaluate(led, r, panel, set(), during).set_index("target")
    assert oc.loc["var_1d", "status"] == "pending"
    assert oc.loc["vol_1m", "status"] == "pending"   # January's last trading day not closed yet


def test_month_forecast_logged_only_after_the_last_trading_day_closes():
    vol = {"month_end": {"date": "2024-01-31", "vol": 0.2, "band90": [0.1, 0.3]}}
    early = datetime(2024, 1, 31, 18, 0, tzinfo=timezone.utc)
    late = datetime(2024, 2, 1, 1, 0, tzinfo=timezone.utc)
    assert [r["target"] for r in M.forecast_rows(SHORT, vol, None, "t", early, "x")] == ["var_1d", "vol_5d"]
    assert "vol_1m" in [r["target"] for r in M.forecast_rows(SHORT, vol, None, "t", late, "x")]


def test_missing_var_is_invalid_not_a_non_breach(tmp_path):
    led = _ledger(tmp_path)
    led.loc[led["target"] == "var_1d", "var95"] = ""
    r = pd.Series([0.0, -0.2], index=pd.bdate_range("2024-01-02", periods=2))
    panel = pd.DataFrame({"rv21": [0.2], "partial": [False]}, index=pd.to_datetime(["2023-12-31"]))
    oc = M.evaluate(led, r, panel, set()).set_index("target")
    assert oc.loc["var_1d", "status"] == "invalid"


def test_band_verdict_uses_an_exact_binomial_test():
    cfg = M.MarketReviewConfig()
    s = pd.DataFrame({"log_error": [0.0] * 24, "in_band": [True] * 24})
    assert M._summ_1m(s, cfg)["verdict"] == "consistent"            # 24/24: p = 0.16
    s2 = pd.DataFrame({"log_error": [0.0] * 24, "in_band": [True] * 17 + [False] * 7})
    assert M._summ_1m(s2, cfg)["verdict"] == "band_miscalibrated"   # 17/24


def test_ids_cover_module_constants(monkeypatch):
    from tcd import short_risk
    a, c = M.short_model_id("har_vix"), M.challenger_model_id("har_vix")
    monkeypatch.setattr(short_risk, "LOGGED", {"rv_d"})
    assert M.short_model_id("har_vix") != a and M.challenger_model_id("har_vix") != c
