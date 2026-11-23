import numpy as np
import pandas as pd

from tcd import fundamentals as fx


def _f(start, end, val, filed, priority=0, form="10-Q"):
    return {"start": pd.Timestamp(start), "end": pd.Timestamp(end), "val": float(val),
            "filed": pd.Timestamp(filed), "form": form, "tag": "T", "priority": priority}


def test_ytd_differencing_derives_q2_q3_q4():
    facts = pd.DataFrame([
        _f("2020-01-01", "2020-03-31", 10, "2020-05-01"),
        _f("2020-01-01", "2020-06-30", 25, "2020-08-01"),  # H1 -> Q2 = 15
        _f("2020-01-01", "2020-09-30", 45, "2020-11-01"),  # 9M -> Q3 = 20
        _f("2020-01-01", "2020-12-31", 70, "2021-02-15", form="10-K"),  # FY -> Q4 = 25
    ])
    q = fx.quarterly(facts).set_index("end")
    assert q.loc["2020-03-31", "val"] == 10
    assert q.loc["2020-06-30", "val"] == 15
    assert q.loc["2020-09-30", "val"] == 20
    assert q.loc["2020-12-31", "val"] == 25
    assert q.loc["2020-12-31", "available"] == pd.Timestamp("2021-02-15")


def test_first_reported_value_wins_over_restatement():
    facts = pd.DataFrame([
        _f("2020-01-01", "2020-03-31", 10, "2020-05-01"),
        _f("2020-01-01", "2020-03-31", 99, "2021-05-01"),  # comparative restated a year later
    ])
    q = fx.quarterly(facts)
    assert len(q) == 1 and q["val"].iloc[0] == 10
    assert q["available"].iloc[0] == pd.Timestamp("2020-05-01")


def test_ttm_respects_filing_dates():
    q = pd.DataFrame({
        "end": pd.to_datetime(["2020-03-31", "2020-06-30", "2020-09-30", "2020-12-31"]),
        "val": [1.0, 2.0, 3.0, 4.0],
        "available": pd.to_datetime(["2020-05-01", "2020-08-01", "2020-11-01", "2021-02-15"]),
    })
    months = pd.date_range("2020-12-31", "2021-03-31", freq="ME")
    ttm = fx.monthly_ttm(q, months)
    assert np.isnan(ttm["2021-01-31"])  # Q4 not yet filed
    assert ttm["2021-02-28"] == 10.0


def test_ttm_rejects_non_consecutive_quarters():
    q = pd.DataFrame({
        "end": pd.to_datetime(["2019-12-31", "2020-06-30", "2020-09-30", "2020-12-31"]),
        "val": [1.0, 2.0, 3.0, 4.0],
        "available": pd.to_datetime(["2020-02-01"] * 4),
    })
    assert np.isnan(fx.monthly_ttm(q, pd.DatetimeIndex(["2021-01-31"])).iloc[0])


def test_chain_link_has_no_jump_when_name_enters():
    idx = pd.date_range("2020-01-31", periods=4, freq="ME")
    num = pd.DataFrame({"A": [1, 1, 1, 1], "B": [1, 1, 1, 1], "C": [1, 1, 1, 1], "D": [np.nan, np.nan, 50, 50]}, index=idx, dtype=float)
    den = pd.DataFrame({"A": [10] * 4, "B": [10] * 4, "C": [10] * 4, "D": [np.nan, np.nan, 100, 100]}, index=idx, dtype=float)
    level, n = fx.chain_link(num, den, min_names=3)
    # Raw ratio jumps from 0.1 to 53/130 when D enters; chained level does not.
    assert np.allclose(level.values, 0.1)
    assert list(n) == [3, 3, 4, 4]


def test_shares_split_adjustment_keeps_market_cap_continuous():
    # 4:1 split on 2020-06-15. Raw price 400 -> 100; raw shares 100 -> 400.
    splits = pd.Series([4.0], index=pd.DatetimeIndex(["2020-06-15"]))
    facts = pd.DataFrame({
        "end": pd.to_datetime(["2020-03-31", "2020-06-30"]),
        "val": [100.0, 400.0],  # Q2 filing already on post-split basis
        "filed": pd.to_datetime(["2020-05-01", "2020-08-01"]),
        "priority": [0, 0],
    })
    months = pd.date_range("2020-05-31", "2020-08-31", freq="ME")
    sh = fx.monthly_shares(facts, splits, months)
    yahoo_close = pd.Series([100.0, 100.0, 100.0, 100.0], index=months)  # split-adjusted, raw 400 -> 100
    mcap = yahoo_close * sh
    assert np.allclose(mcap.values, 40_000.0)


def test_split_between_period_end_and_filing_is_not_double_counted():
    splits = pd.Series([10.0], index=pd.DatetimeIndex(["2024-06-10"]))
    facts = pd.DataFrame({"end": [pd.Timestamp("2024-04-28")], "val": [2_460.0],  # retroactively adjusted in filing
                          "filed": [pd.Timestamp("2024-08-28")], "priority": [0]})
    sh = fx.monthly_shares(facts, splits, pd.DatetimeIndex(["2024-08-31"]))
    assert sh.iloc[0] == 2_460.0
