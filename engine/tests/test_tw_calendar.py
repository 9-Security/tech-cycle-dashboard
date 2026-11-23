import pandas as pd

from tcd import tw_calendar


def _df(dates, closes):
    s = pd.Series(closes, index=pd.DatetimeIndex(dates), dtype=float)
    return pd.DataFrame({"close": s, "adjclose": s})


def test_clean_drops_holiday_bars_only_inside_index_window():
    wl = {"stocks": [{"symbol": "A.TW", "market": "TW"}, {"symbol": "U", "market": "US"}]}
    twii = _df(["2024-01-02", "2024-01-03", "2024-01-05", "2024-01-08", "2024-01-09"], [100, 101, 101, 102, 103])
    # 01-04: index has no bar (holiday); 01-05: index unchanged (typhoon closure);
    # 2023-12-29: before the index window; 01-10: after it (index lags) -> kept.
    a = _df(["2023-12-29", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08", "2024-01-09", "2024-01-10"],
            [9, 10, 11, 11, 11, 12, 13, 14])
    u = _df(["2024-01-04"], [5])
    out, rep = tw_calendar.clean({"^TWII": twii, "A.TW": a, "U": u}, wl)
    assert [str(d.date()) for d in out["A.TW"].index] == ["2023-12-29", "2024-01-02", "2024-01-03", "2024-01-08", "2024-01-09", "2024-01-10"]
    assert out["U"] is u and rep["total"] == 2 and rep["by_symbol"]["A.TW"]["last"] == ["2024-01-04", "2024-01-05"]


def test_clean_is_noop_without_index():
    wl = {"stocks": [{"symbol": "A.TW", "market": "TW"}]}
    a = _df(["2024-01-02"], [1])
    out, rep = tw_calendar.clean({"A.TW": a}, wl)
    assert out["A.TW"] is a and rep["applied"] is False
