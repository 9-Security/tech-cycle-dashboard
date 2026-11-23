"""Remove carried-forward Yahoo bars on Taiwan market holidays.

Yahoo's daily series for Taiwan stocks contain bars on days the exchange
did not trade (national holidays, Lunar New Year, typhoon closures): mostly
the previous close repeated, sometimes a spurious price. The TAIEX series
(^TWII) from the same source does not have these bars, and its calendar
matched the official TWSE calendar wherever the official list was complete
(2025: 243/243 days; it never showed a bar on an official closure).

Rule (data layer, applied before the stock model; the model code and its
fingerprint are unchanged): inside the TAIEX coverage window, a Taiwan stock
bar is dropped if
  * ^TWII has no bar that day, or
  * ^TWII's close is exactly unchanged from its previous bar (a market-wide
    closure carried forward in the index too: e.g. typhoon days).
Bars before the first or after the last ^TWII bar are kept (no evidence
either way; the latter guards against an index series that lags a day).
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

RULE = ("Taiwan stock bars dropped inside the ^TWII window when ^TWII has no bar that day or its close is "
        "unchanged from the previous bar (market closed; Yahoo carried a price forward)")


def market_open_days(twii_close: pd.Series) -> pd.DatetimeIndex:
    c = twii_close.dropna()
    return c.index[~(c.diff() == 0)]


def clean(prices: dict[str, pd.DataFrame], watchlist: dict, benchmark: str = "^TWII",
          max_listed: int = 5) -> tuple[dict[str, pd.DataFrame], dict]:
    """Return (prices with Taiwan holiday bars removed, report). Other symbols are untouched."""
    b = prices.get(benchmark)
    if b is None or b["close"].dropna().empty:
        log.warning("tw calendar: %s missing, Taiwan bars not cleaned", benchmark)
        return prices, {"rule": RULE, "applied": False, "reason": f"{benchmark} missing"}
    open_days = market_open_days(b["close"])
    lo, hi = b["close"].dropna().index[0], b["close"].dropna().index[-1]
    out, dropped = dict(prices), {}
    for spec in watchlist["stocks"]:
        s = spec["symbol"]
        if spec["market"] != "TW" or s not in prices:
            continue
        df = prices[s]
        idx = df.index
        inside = (idx >= lo) & (idx <= hi)
        bad = inside & ~idx.isin(open_days)
        if bad.any():
            out[s] = df[~bad]
            dropped[s] = {"n": int(bad.sum()), "last": [str(d.date()) for d in idx[bad][-max_listed:]]}
    total = sum(v["n"] for v in dropped.values())
    log.info("tw calendar: dropped %d holiday bars across %d Taiwan stocks", total, len(dropped))
    return out, {"rule": RULE, "applied": True, "window": [str(lo.date()), str(hi.date())],
                 "total": total, "by_symbol": dropped}
