"""Fill a missing final close on Yahoo's latest daily bar (methodology section 7).

Yahoo sometimes publishes the latest US daily bar with a NULL close for hours
after the session (seen 2026-11-23 for XLK, SPY, QQQ, NVDA ...), while the same
response's `meta.regularMarketPrice` already holds the closing price. The bar
is then dropped and the whole site stays one day behind.

Rule (owner decision 2026-11-24, option A): the missing close is filled from
`meta.regularMarketPrice` only if ALL hold
  * the null bar is the LAST bar, and `meta.regularMarketTime` falls on that
    bar's exchange-local date at or after the regular session end;
  * the symbol is US-listed (no index `^`, no `.TW` / `.TWO` suffix);
  * no dividend or split event is dated on that bar (adjusted history would
    not yet reflect it);
  * Nasdaq's quote API independently reports the official close of the SAME
    date ("Closed at <date> 4:00 PM ET") within TOLERANCE of Yahoo's price.
Otherwise the bar stays dropped (fail closed). Every attempt is recorded in
LOG and published in health.json -> close_fills.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone

import pandas as pd

from .sources.http import FetchError
from .sources.store import RawStore

log = logging.getLogger(__name__)

TOLERANCE = 0.0025  # 0.25%: consolidated vs primary-listing close differ by far less
INFO_URL = "https://api.nasdaq.com/api/quote/{symbol}/info"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; tech-cycle-dashboard research)", "Accept": "application/json"}
LOG: list[dict] = []


def reset() -> None:
    LOG.clear()


def pending(result: dict) -> dict | None:
    """The last bar's missing close, if Yahoo's meta shows the session ended."""
    try:
        ts = result["timestamp"]
        close = result["indicators"]["quote"][0]["close"]
        meta = result["meta"]
        off = int(meta.get("gmtoffset", 0))
        price, mtime = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
        end = ((meta.get("currentTradingPeriod") or {}).get("regular") or {}).get("end")
    except (KeyError, IndexError, TypeError):
        return None
    if not ts or close[-1] is not None or price is None or mtime is None or end is None:
        return None
    local = lambda t: datetime.fromtimestamp(int(t) + off, timezone.utc)  # noqa: E731
    bar, quote_t, end_t = local(ts[-1]), local(mtime), local(end)
    end_tod = timedelta(hours=end_t.hour, minutes=end_t.minute)
    same_day = quote_t.date() == bar.date()
    after_close = timedelta(hours=quote_t.hour, minutes=quote_t.minute, seconds=quote_t.second) >= end_tod
    if not (same_day and after_close):
        return None
    events = result.get("events") or {}
    ev_days = {local(e["date"]).date() for k in ("dividends", "splits") for e in (events.get(k) or {}).values()
               if "date" in e}
    return {"date": str(bar.date()), "price": float(price), "event_on_day": bar.date() in ev_days}


def us_listed(symbol: str) -> bool:
    return not symbol.startswith("^") and "." not in symbol and "=" not in symbol  # no indices, TW, FX


def _closed_at(text: str) -> pd.Timestamp | None:
    m = re.search(r"Closed at (\w{3} \d{1,2}, \d{4}) 4:00 PM ET", text or "")
    return pd.Timestamp(datetime.strptime(m.group(1), "%b %d, %Y")) if m else None


def official_close(d: dict) -> tuple[pd.Timestamp | None, float | None]:
    """(date, close) from a Nasdaq quote: the after-hours view carries the official
    close in secondaryData ("Closed at <date> 4:00 PM ET"); the closed-market view
    carries it in primaryData ("<date>", market status Closed)."""
    def px(x):
        t = re.sub(r"[^\d.]", "", str(x or ""))
        return float(t) if t else None
    sec = d.get("secondaryData") or {}
    when = _closed_at(sec.get("lastTradeTimestamp") or "")
    if when is not None and px(sec.get("lastSalePrice")) is not None:
        return when, px(sec.get("lastSalePrice"))
    pri = d.get("primaryData") or {}
    ts = str(pri.get("lastTradeTimestamp") or "").strip()
    if d.get("marketStatus") == "Closed" and re.fullmatch(r"\w{3} \d{1,2}, \d{4}", ts) and px(pri.get("lastSalePrice")):
        return pd.Timestamp(datetime.strptime(ts, "%b %d, %Y")), px(pri.get("lastSalePrice"))
    return None, None


def nasdaq_close(store: RawStore, symbol: str, day: str) -> tuple[float | None, str | None]:
    """Official close of `day` from Nasdaq's quote API, or (None, reason)."""
    last_err = None
    for ac in ("stocks", "etf"):
        try:
            raw = store.get(f"nasdaq_info_{symbol}_{ac}_{day.replace('-', '')}.json", INFO_URL.format(symbol=symbol),
                            headers=HEADERS, params={"assetclass": ac})
            d = (json.loads(raw).get("data") or {})
        except (FetchError, json.JSONDecodeError) as exc:
            last_err = type(exc).__name__
            continue
        if not d:
            continue
        when, px = official_close(d)
        if when is None:
            return None, "no official close in Nasdaq quote"
        if str(when.date()) != day:
            return None, f"Nasdaq close is for {when.date()}"
        return px, None
    return None, f"Nasdaq quote unavailable ({last_err or 'unknown symbol'})"


def apply(df: pd.DataFrame, result: dict, symbol: str, store: RawStore | None) -> pd.DataFrame:
    p = pending(result)
    if p is None:
        return df
    rec = {"symbol": symbol, "date": p["date"], "yahoo": p["price"], "nasdaq": None, "filled": False}
    if not us_listed(symbol):
        rec["reason"] = "not a US-listed symbol"
    elif p["event_on_day"]:
        rec["reason"] = "dividend or split on that day"
    elif store is None:
        rec["reason"] = "no store for the second source"
    else:
        nq, why = nasdaq_close(store, symbol, p["date"])
        rec["nasdaq"] = nq
        if nq is None:
            rec["reason"] = why
        elif abs(p["price"] / nq - 1) > TOLERANCE:
            rec["reason"] = f"differs from Nasdaq by {abs(p['price'] / nq - 1):.2%}"
        else:
            day = pd.Timestamp(p["date"])
            if day not in df.index and (df.empty or day > df.index[-1]):
                row = pd.DataFrame({"close": [p["price"]], "adjclose": [p["price"]]},
                                   index=pd.DatetimeIndex([day], name="date"))
                df = pd.concat([df, row])
                rec["filled"] = True
            else:
                rec["reason"] = "bar already present"
    LOG.append(rec)
    log.info("close fill %s %s: %s", symbol, p["date"], "filled" if rec["filled"] else rec.get("reason"))
    return df
