from datetime import datetime, timezone

import numpy as np
import pandas as pd

from tcd import feed


def _px(n=300, end="2024-01-03"):
    idx = pd.bdate_range(end=end, periods=n)
    c = pd.Series(np.linspace(100, 130, n), index=idx)
    return pd.DataFrame({"close": c, "adjclose": c})


def test_feed_has_every_symbol_and_only_final_bars():
    prices = {s: _px() for s in feed.ETFS + feed.STOCKS + feed.TW_STOCKS}
    status = {"light": {"date": "2024-01-02", "level": "red", "var95": 0.05}, "exposure_cap": {"cap": 0.35, "band": "D"},
              "weights": {"executed_weight": 1.0}}
    vix = pd.Series([20.0], index=pd.to_datetime(["2024-01-02"]))
    during = datetime(2024, 1, 3, 18, 0, tzinfo=timezone.utc)  # 2024-01-03 still trading
    fx = pd.DataFrame({"close": [31.0, 31.2, 31.5]}, index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    f = feed.build(prices, status, [{"symbol": "NVDA", "level": "red", "var95": 0.07}], 0.16, vix, vix, "t", during, fx=fx)
    assert f["schema"] == "range-feed/2" and f["missing"] == [] and len(f["symbols"]) == 37
    assert f["fx"]["date"] == "2024-01-02" and f["fx"]["rate"] == 31.2  # today's (UTC) FX bar left out
    tw = f["symbols"]["2330.TW"]
    assert tw["market"] == "TW" and tw["currency"] == "TWD" and tw["date"] == "2024-01-03"  # TW 01-03 final at 18:00 UTC
    x = f["symbols"]["NVDA"]
    assert x["date"] == "2024-01-02" and len(x["history"]["adjclose"]) == feed.HISTORY_DAYS
    assert x["history"]["dates"][-1] == "2024-01-02" and x["risk"]["level"] == "red" and x["kind"] == "stock"
    assert f["market"]["exposure_cap"] == 0.35 and f["rules"]["rules_version"] == "1.0"


def test_missing_symbol_is_listed():
    f = feed.build({"XLK": _px()}, {}, None, None, pd.Series(dtype=float), pd.Series(dtype=float), "t",
                   datetime(2024, 1, 4, tzinfo=timezone.utc))
    assert list(f["symbols"]) == ["XLK"] and "SPY" in f["missing"] and "2330.TW" in f["missing"]
    assert f["market"]["vix"] is None and f["fx"] is None


def test_public_feed_has_no_price_series():
    prices = {s: _px() for s in feed.ETFS + feed.STOCKS + feed.TW_STOCKS}
    status = {"light": {"date": "2024-01-02", "level": "red"}, "exposure_cap": {"cap": 0.35, "band": "D"}}
    fx = pd.DataFrame({"close": [31.0, 31.2]}, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    full = feed.build(prices, status, None, None, pd.Series(dtype=float), pd.Series(dtype=float), "t",
                      datetime(2024, 1, 4, tzinfo=timezone.utc), fx=fx)
    pub = feed.public(full)
    assert pub["schema"] == "range-feed/3" and full["schema"] == "range-feed/2"
    x = pub["symbols"]["XLK"]
    assert "history" not in x and set(x) >= {"close", "ret_1d", "ret_20d", "ret_250d", "vol_20d_ann", "from_high_260d"}
    assert abs(x["ret_1d"] - (130 / (130 - 30 / 299) - 1)) < 1e-4
    assert pub["fx"] == {"pair": "USD/TWD", "unit": "TWD per USD", "date": "2024-01-02", "rate": 31.2}
    assert "history" not in str(pub)


def test_vix_only_final_days():
    vix = pd.Series([20.0, 21.0, 30.0], index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    during = datetime(2024, 1, 3, 18, 0, tzinfo=timezone.utc)  # 2024-01-03 session still open
    f = feed.build({"XLK": _px()}, {}, None, None, vix, pd.Series(dtype=float), "t", during)
    assert f["market"]["vix"] == 21.0 and f["market"]["vix_date"] == "2024-01-02"
