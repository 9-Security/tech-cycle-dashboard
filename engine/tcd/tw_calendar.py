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
Bars before the first ^TWII bar are kept (no evidence). Bars after the last
^TWII bar are kept only if their close moved (guards against an index series
that lags a day, while dropping the carried-forward bar Yahoo emits on a
weekday closure).

Index missing on a trading day (2026-11-25 fix): Yahoo sometimes returns a
^TWII row with a null close (the loader drops it, so the day has no index bar)
although the exchange traded. Most index gaps are real closures, so a day
inside the window without a usable ^TWII close counts as open only when the
stocks themselves show it: at least MIN_NAMES Taiwan stocks have a bar that
day and at least MOVED_SHARE of them closed at a different price than their
previous bar. Over the 138 such days since 1997 the highest share otherwise
was 56% (2012-01-02 holiday, 9 of 16) or a single name; 2026-11-25 had 18/18.
"""

from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

RULE = ("Taiwan stock bars dropped inside the ^TWII window when ^TWII has no bar that day or its close is "
        "unchanged from the previous bar (market closed; Yahoo carried a price forward); a day without a ^TWII "
        "close counts as open only if >= 5 Taiwan stocks have a bar and >= 80% of them moved")


MIN_NAMES, MOVED_SHARE = 5, 0.8


def market_open_days(twii_close: pd.Series) -> pd.DatetimeIndex:
    c = twii_close.dropna()
    return c.index[~(c.diff() == 0)]


def index_gap_days(twii_close: pd.Series, prices: dict[str, pd.DataFrame], tw_symbols: list[str]) -> dict:
    """Days inside the ^TWII window with a Taiwan stock bar but no usable ^TWII close,
    each with the stocks' evidence: {date: {moved, of, open}}."""
    c_idx = twii_close.dropna()
    if c_idx.empty:
        return {}
    lo, hi, have = c_idx.index[0], c_idx.index[-1], set(c_idx.index)
    closes = {s: prices[s]["close"].dropna() for s in tw_symbols}
    days = sorted({d for c in closes.values() for d in c.index if lo <= d <= hi and d not in have})
    out = {}
    for d in days:
        moved = of = 0
        for c in closes.values():
            if d not in c.index:
                continue
            prev = c[c.index < d]
            if prev.empty:
                continue
            of += 1
            moved += bool(c.loc[d] != prev.iloc[-1])
        out[d] = {"moved": moved, "of": of, "open": of >= MIN_NAMES and moved >= MOVED_SHARE * of}
    return out


def clean(prices: dict[str, pd.DataFrame], watchlist: dict, benchmark: str = "^TWII",
          max_listed: int = 5) -> tuple[dict[str, pd.DataFrame], dict]:
    """Return (prices with Taiwan holiday bars removed, report). Other symbols are untouched."""
    b = prices.get(benchmark)
    if b is None or b["close"].dropna().empty:
        log.warning("tw calendar: %s missing, Taiwan bars not cleaned", benchmark)
        return prices, {"rule": RULE, "applied": False, "reason": f"{benchmark} missing"}
    open_days = market_open_days(b["close"])
    lo, hi = b["close"].dropna().index[0], b["close"].dropna().index[-1]
    tw = [x["symbol"] for x in watchlist["stocks"] if x["market"] == "TW" and x["symbol"] in prices]
    gaps = index_gap_days(b["close"], prices, tw)
    recovered = sorted(d for d, v in gaps.items() if v["open"])
    if recovered:
        open_days = open_days.union(pd.DatetimeIndex(recovered))
        log.warning("tw calendar: %s has no close on %s but the stocks traded; kept as open day(s)",
                    benchmark, ", ".join(str(d.date()) for d in recovered))
    out, dropped = dict(prices), {}
    for spec in watchlist["stocks"]:
        s = spec["symbol"]
        if spec["market"] != "TW" or s not in prices:
            continue
        df = prices[s]
        idx = df.index
        inside = (idx >= lo) & (idx <= hi)
        bad = inside & ~idx.isin(open_days)
        # After the last ^TWII bar: keep a bar only if its close moved (an
        # unchanged close there is the typical carried-forward holiday bar,
        # e.g. a typhoon day while ^TWII still ends the day before).
        after = idx > hi
        if after.any():
            c = df["close"]
            bad |= after & (c == c.shift(1)).to_numpy()
        if bad.any():
            out[s] = df[~bad]
            dropped[s] = {"n": int(bad.sum()), "last": [str(d.date()) for d in idx[bad][-max_listed:]]}
    total = sum(v["n"] for v in dropped.values())
    log.info("tw calendar: dropped %d holiday bars across %d Taiwan stocks", total, len(dropped))
    return out, {"rule": RULE, "applied": True, "window": [str(lo.date()), str(hi.date())],
                 "total": total, "by_symbol": dropped,
                 "index_gap_open_days": {str(d.date()): gaps[d] for d in recovered}}
