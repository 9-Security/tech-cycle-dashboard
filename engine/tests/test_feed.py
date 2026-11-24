from datetime import datetime, timezone

import numpy as np
import pandas as pd

from tcd import feed


def _px(n=300, end="2024-01-03"):
    idx = pd.bdate_range(end=end, periods=n)
    c = pd.Series(np.linspace(100, 130, n), index=idx)
    return pd.DataFrame({"close": c, "adjclose": c})


def test_feed_has_every_symbol_and_only_final_bars():
    prices = {s: _px() for s in feed.ETFS + feed.STOCKS}
    status = {"light": {"date": "2024-01-02", "level": "red", "var95": 0.05}, "exposure_cap": {"cap": 0.35, "band": "D"},
              "weights": {"executed_weight": 1.0}}
    vix = pd.Series([20.0], index=pd.to_datetime(["2024-01-02"]))
    during = datetime(2024, 1, 3, 18, 0, tzinfo=timezone.utc)  # 2024-01-03 still trading
    f = feed.build(prices, status, [{"symbol": "NVDA", "level": "red", "var95": 0.07}], 0.16, vix, vix, "t", during)
    assert f["schema"] == "range-feed/1" and f["missing"] == [] and len(f["symbols"]) == 19
    x = f["symbols"]["NVDA"]
    assert x["date"] == "2024-01-02" and len(x["history"]["adjclose"]) == feed.HISTORY_DAYS
    assert x["history"]["dates"][-1] == "2024-01-02" and x["risk"]["level"] == "red" and x["kind"] == "stock"
    assert f["market"]["exposure_cap"] == 0.35 and f["rules"]["cost_bps"] == 15


def test_missing_symbol_is_listed():
    f = feed.build({"XLK": _px()}, {}, None, None, pd.Series(dtype=float), pd.Series(dtype=float), "t",
                   datetime(2024, 1, 4, tzinfo=timezone.utc))
    assert list(f["symbols"]) == ["XLK"] and "SPY" in f["missing"] and f["market"]["vix"] is None
