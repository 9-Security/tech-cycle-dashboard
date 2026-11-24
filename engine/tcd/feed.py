"""Daily data feed for the private agent paper-trading range (data/feed.json).

Schema "range-feed/1". Read-only for agents; the range settles trades with the
prices published here (second-source checked, archived in R2). Only FINAL US
bars are included (bar_is_final), so the feed never carries an unfinished day.

    data_as_of   date of the latest final XLK bar (the market numbers' date)
    rules        the range's fixed rules (informational; the range repo enforces them)
    market       risk light, VaR, exposure cap, v2 / v3 weights, VIX
    symbols      per tradable symbol: last final bar + last HISTORY_DAYS adjusted
                 closes (oldest first) + the stock monitor's risk fields (stocks)
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from .ledger import bar_is_final

SCHEMA = "range-feed/1"
ETFS = ("XLK", "SPY", "XLF", "XLE", "XLV", "EWJ", "EWG", "EWU", "EEM")
STOCKS = ("AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "AVGO", "AMD", "ORCL", "INTC")
HISTORY_DAYS = 260
RULES = {"currency": "USD", "initial_cash": 1_000_000, "long_only": True, "max_gross": 1.0,
         "max_single_stock": 0.30, "cost_bps": 15, "min_weight_change": 0.01,
         "fill": "close of the next US trading day after the freeze", "freeze_utc": "13:00 on the next trading day",
         "cash_rate": "3-month T-bill (FRED DTB3)"}
STOCK_FIELDS = ("level", "vol_1d_ann", "var95", "vol_percentile", "beta_1y", "ret_1m", "from_52w_high")


def _r(x, n=6):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return round(v, n) if np.isfinite(v) else None


def series_block(px: pd.DataFrame, now_utc: datetime) -> dict | None:
    c = px[["close", "adjclose"]].dropna()
    c = c[~c.index.duplicated(keep="last")].sort_index()
    while len(c) and not bar_is_final("US", str(c.index[-1].date()), now_utc):
        c = c.iloc[:-1]  # never publish an unfinished bar
    if c.empty:
        return None
    h = c["adjclose"].iloc[-HISTORY_DAYS:]
    return {"date": str(c.index[-1].date()), "close": _r(c["close"].iloc[-1]), "adjclose": _r(c["adjclose"].iloc[-1]),
            "history": {"start": str(h.index[0].date()), "dates": [str(d.date()) for d in h.index],
                        "adjclose": [_r(v) for v in h.to_numpy()]}}


def build(prices: dict[str, pd.DataFrame], status: dict, stock_rows: list[dict] | None, v3_weight, vix: pd.Series,
          tbill: pd.Series, as_of: str, now_utc: datetime) -> dict:
    by = {r["symbol"]: r for r in (stock_rows or [])}
    syms, missing = {}, []
    for s in ETFS + STOCKS:
        blk = series_block(prices[s], now_utc) if s in prices else None
        if blk is None:
            missing.append(s)
            continue
        blk["kind"] = "etf" if s in ETFS else "stock"
        if s in by:
            blk["risk"] = {k: (by[s].get(k) if k == "level" else _r(by[s].get(k))) for k in STOCK_FIELDS}
        syms[s] = blk
    L, C = status.get("light") or {}, status.get("exposure_cap") or {}
    w = status.get("weights") or {}
    v, tb = vix.dropna(), tbill.dropna()
    return {
        "schema": SCHEMA, "generated_at": as_of, "data_as_of": L.get("date"),
        "rules": RULES,
        "market": {"light": L.get("level"), "vol_percentile": _r(L.get("vol_percentile")), "var95_1d": _r(L.get("var95")),
                   "vol_1d_ann": _r(L.get("vol_ann")), "exposure_cap": C.get("cap"), "exposure_band": C.get("band"),
                   "v2_weight": _r(w.get("executed_weight")), "v3_weight": _r(v3_weight),
                   "vix": _r(v.iloc[-1]) if len(v) else None, "vix_date": str(v.index[-1].date()) if len(v) else None,
                   "tbill_3m_pct": _r(tb.iloc[-1]) if len(tb) else None,
                   "tbill_date": str(tb.index[-1].date()) if len(tb) else None},
        "symbols": syms, "missing": missing,
        "notes": "Research data, simulation only. Not investment advice.",
    }
