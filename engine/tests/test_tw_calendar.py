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


def test_bar_after_index_end_dropped_only_if_unchanged():
    wl = {"stocks": [{"symbol": "A.TW", "market": "TW"}, {"symbol": "B.TW", "market": "TW"}]}
    twii = _df(["2026-10-21", "2026-10-22"], [100, 101])
    a = _df(["2026-10-21", "2026-10-22", "2026-10-23"], [10, 11, 11])   # carried forward on a closure
    b = _df(["2026-10-21", "2026-10-22", "2026-10-23"], [10, 11, 12])   # index lags; real move kept
    out, _ = tw_calendar.clean({"^TWII": twii, "A.TW": a, "B.TW": b}, wl)
    assert list(out["A.TW"].index.strftime("%Y-%m-%d")) == ["2026-10-21", "2026-10-22"]
    assert len(out["B.TW"]) == 3


def _null_index_case(n_moved: int, n: int = 6):
    days = ["2026-11-20", "2026-11-23", "2026-11-24", "2026-11-25", "2026-11-26"]
    twii = _df(days, [100, 101, 102, float("nan"), 103])
    wl = {"stocks": [{"symbol": f"S{i}.TW", "market": "TW"} for i in range(n)]}
    px = {"^TWII": twii}
    for i in range(n):
        last = 11.5 if i < n_moved else 11.0   # moved on 11-25, or carried forward
        px[f"S{i}.TW"] = _df(days, [10, 10.5, 11, last, 12])
    return px, wl


def test_null_index_close_kept_when_the_stocks_traded():
    # 2026-11-25: Yahoo ^TWII close was null while every Taiwan stock traded.
    px, wl = _null_index_case(n_moved=6)
    out, rep = tw_calendar.clean(px, wl)
    assert "2026-11-25" in out["S0.TW"].index.strftime("%Y-%m-%d")
    assert rep["total"] == 0
    assert rep["null_index_open_days"] == {"2026-11-25": {"moved": 6, "of": 6, "open": True}}


def test_null_index_close_still_a_holiday_without_broad_evidence():
    # A holiday with some spurious prices (e.g. 2012-01-02: 9 of 16 moved) stays closed.
    px, wl = _null_index_case(n_moved=4)
    out, rep = tw_calendar.clean(px, wl)
    assert "2026-11-25" not in out["S0.TW"].index.strftime("%Y-%m-%d")
    assert rep["total"] == 6 and rep["null_index_open_days"] == {}


def test_null_index_close_needs_enough_names():
    px, wl = _null_index_case(n_moved=4, n=4)   # 100% moved but only 4 names
    out, rep = tw_calendar.clean(px, wl)
    assert "2026-11-25" not in out["S0.TW"].index.strftime("%Y-%m-%d") and rep["null_index_open_days"] == {}
