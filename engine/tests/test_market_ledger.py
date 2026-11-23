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
