"""Daily data feed for the private agent paper-trading range (data/feed.json).

Two outputs (2026-11-24, owner decision "B"):
  * PUBLIC  data/feed.json, schema "range-feed/3": per-symbol SUMMARIES only
    (last close, returns, 20-day volatility, drawdown, risk fields) and the latest
    USD/TWD - no vendor price series are redistributed.
  * PRIVATE full feed, schema "range-feed/2": the same plus 260 adjusted closes per
    symbol and the USD/TWD history; written to the cache and uploaded only to the
    private R2 bucket (feeds/latest.json), where the private range reads it to settle.
Only FINAL bars of each market are included (bar_is_final).

    data_as_of   date of the latest final XLK bar (the market numbers' date)
    rules        the range's fixed rules (informational; the range repo enforces them)
    market       risk light, VaR, exposure cap, v2 / v3 weights, VIX
    symbols      per tradable symbol: last final bar + last HISTORY_DAYS adjusted
                 closes (oldest first) + the stock monitor's risk fields (stocks);
                 `market` US / TW and `currency` USD / TWD
    fx           USD/TWD (TWD per USD), Yahoo TWD=X, complete UTC days only
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from .ledger import bar_is_final

SCHEMA = "range-feed/2"          # private full feed
PUBLIC_SCHEMA = "range-feed/3"   # public summaries
ETFS = ("XLK", "SPY", "XLF", "XLE", "XLV", "EWJ", "EWG", "EWU", "EEM")
STOCKS = ("AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "AMD", "ORCL", "INTC")
TW_STOCKS = ("2330.TW", "2454.TW", "3661.TW", "3443.TW", "2317.TW", "2382.TW", "3231.TW", "6669.TW", "2356.TW",
             "2308.TW", "3017.TW", "3324.TWO", "2059.TW", "2345.TW", "2383.TW", "3037.TW", "3711.TW", "3131.TWO")
FX_SYMBOL = "TWD=X"
HISTORY_DAYS = 260
RULES = {"rules_version": "1.0", "see": "agent-range README (authoritative)"}  # informational only
STOCK_FIELDS = ("level", "vol_1d_ann", "var95", "vol_percentile", "beta_1y", "ret_1m", "from_52w_high")


def _r(x, n=6):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, n) if np.isfinite(v) else None


def series_block(px: pd.DataFrame, now_utc: datetime, market: str = "US") -> dict | None:
    c = px[["close", "adjclose"]].dropna()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    while len(c) and not bar_is_final(market, str(c.index[-1].date()), now_utc):
        c = c.iloc[:-1]  # never publish an unfinished bar
    if c.empty:
        return None
    h = c["adjclose"].iloc[-HISTORY_DAYS:]
    return {"date": str(c.index[-1].date()), "close": _r(c["close"].iloc[-1]), "adjclose": _r(c["adjclose"].iloc[-1]),
            "history": {"start": str(h.index[0].date()), "dates": [str(d.date()) for d in h.index],
                        "adjclose": [_r(v) for v in h.to_numpy()]}}


def fx_block(fx: pd.DataFrame | None, now_utc: datetime) -> dict | None:
    """TWD per USD; today's (UTC) bar is still trading and is left out."""
    if fx is None or fx.empty:
        return None
    c = fx["close"].dropna()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    c = c[c.index < pd.Timestamp(now_utc.date())].iloc[-HISTORY_DAYS:]
    if c.empty:
        return None
    return {"pair": "USD/TWD", "unit": "TWD per USD", "date": str(c.index[-1].date()), "rate": _r(c.iloc[-1]),
            "history": {"dates": [str(d.date()) for d in c.index], "rate": [_r(v) for v in c.to_numpy()]}}


def build(prices: dict[str, pd.DataFrame], status: dict, stock_rows: list[dict] | None, v3_weight, vix: pd.Series,
          tbill: pd.Series, as_of: str, now_utc: datetime, fx: pd.DataFrame | None = None) -> dict:
    by = {r["symbol"]: r for r in (stock_rows or [])}
    syms, missing = {}, []
    for s in ETFS + STOCKS + TW_STOCKS:
        mkt = "TW" if s in TW_STOCKS else "US"
        blk = series_block(prices[s], now_utc, mkt) if s in prices else None
        if blk is None:
            missing.append(s)
            continue
        blk["kind"] = "etf" if s in ETFS else "stock"
        blk["market"], blk["currency"] = mkt, ("TWD" if mkt == "TW" else "USD")
        if s in by:
            blk["risk"] = {k: (by[s].get(k) if k == "level" else _r(by[s].get(k))) for k in STOCK_FIELDS}
        syms[s] = blk
    L, C = status.get("light") or {}, status.get("exposure_cap") or {}
    w = status.get("weights") or {}
    v, tb = vix.dropna(), tbill.dropna()
    # VIX is a US index: only CLOSED days, like every price in the feed (Yahoo creates the
    # day's bar before the session ends).
    v = v[[bar_is_final("US", str(d.date()), now_utc) for d in v.index]] if len(v) else v
    return {
        "schema": SCHEMA, "generated_at": as_of, "data_as_of": L.get("date"),
        "rules": RULES,
        "market": {"light": L.get("level"), "vol_percentile": _r(L.get("vol_percentile")), "var95_1d": _r(L.get("var95")),
                   "vol_1d_ann": _r(L.get("vol_ann")), "exposure_cap": C.get("cap"), "exposure_band": C.get("band"),
                   "v2_weight": _r(w.get("executed_weight")), "v3_weight": _r(v3_weight),
                   "vix": _r(v.iloc[-1]) if len(v) else None, "vix_date": str(v.index[-1].date()) if len(v) else None,
                   "tbill_3m_pct": _r(tb.iloc[-1]) if len(tb) else None,
                   "tbill_date": str(tb.index[-1].date()) if len(tb) else None},
        "symbols": syms, "missing": missing, "fx": fx_block(fx, now_utc),
        "notes": "Research data, simulation only. Not investment advice.",
    }


def _summary(blk: dict) -> dict:
    raw = blk["history"]["adjclose"]
    filled, last = [], None
    for x in raw:  # a missing close repeats the last one: windows stay on the trading calendar
        last = x if x else last
        filled.append(last)
    p = [x for x in filled if x is not None]
    ret = lambda n: (_r(filled[-1] / filled[-1 - n] - 1, 4)  # noqa: E731
                     if len(filled) > n and filled[-1 - n] else None)
    r = [p[i] / p[i - 1] - 1 for i in range(1, len(p))][-20:]
    mu = sum(r) / len(r) if r else 0.0
    vol = (sum((x - mu) ** 2 for x in r) / len(r) * 252) ** 0.5 if r else None
    out = {k: blk.get(k) for k in ("kind", "market", "currency", "date", "close")}
    out.update(ret_1d=ret(1), ret_5d=ret(5), ret_20d=ret(20), ret_60d=ret(60), ret_250d=ret(250),
               vol_20d_ann=_r(vol, 4), from_high_260d=_r(p[-1] / max(p) - 1, 4) if p else None)
    if "risk" in blk:
        out["risk"] = blk["risk"]
    return out


def public(full: dict) -> dict:
    """The public data/feed.json: summaries only (no price or FX series)."""
    fx = full.get("fx") or {}
    return {**{k: v for k, v in full.items() if k not in ("symbols", "fx", "schema")},
            "schema": PUBLIC_SCHEMA,
            "symbols": {s: _summary(b) for s, b in full["symbols"].items()},
            "fx": {k: fx.get(k) for k in ("pair", "unit", "date", "rate")} if fx else None,
            "full_feed": "private: the range settles with the full price series held in a private bucket"}
