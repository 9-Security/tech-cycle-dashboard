"""Yahoo Finance chart API (daily bars, adjusted close)."""

from __future__ import annotations

import json
from urllib.parse import quote

import pandas as pd

from .http import FetchError
from .store import RawStore

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
# Yahoo rejects some non-browser agents; this header carries no personal data.
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; tech-cycle-dashboard/2.0)"}


def fetch_daily(store: RawStore, symbol: str) -> pd.DataFrame:
    """Return DataFrame indexed by exchange-local date with close/adjclose."""
    name = f"yahoo_{symbol.replace('^', 'IDX_')}.json"
    raw = store.get(
        name,
        CHART_URL.format(symbol=quote(symbol)),
        headers=HEADERS,
        params={"period1": 0, "period2": 9_999_999_999, "interval": "1d", "events": "div,split"},
    )
    return parse_chart(raw, symbol)


def parse_chart(raw: bytes, symbol: str) -> pd.DataFrame:
    try:
        payload = json.loads(raw)
        result = payload["chart"]["result"][0]
        ts = result["timestamp"]
        quote_ = result["indicators"]["quote"][0]
        adj = result["indicators"].get("adjclose", [{}])[0].get("adjclose")
        offset = int(result["meta"].get("gmtoffset", 0))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise FetchError(f"yahoo {symbol}: unexpected payload ({exc})") from exc

    dates = pd.to_datetime(pd.Series(ts, dtype="int64") + offset, unit="s").dt.normalize()
    df = pd.DataFrame(
        {"close": quote_["close"], "adjclose": adj if adj is not None else quote_["close"]},
        index=pd.DatetimeIndex(dates, name="date"),
    ).astype(float)
    df = df[~df.index.duplicated(keep="last")].dropna(subset=["close"]).sort_index()
    if df.empty:
        raise FetchError(f"yahoo {symbol}: no rows")
    return df


def parse_splits(raw: bytes) -> pd.Series:
    """Split events as ratio (new shares per old share), indexed by date.

    Yahoo's `close` is retroactively split-adjusted, so any share count must
    be scaled by the splits that happened after it was reported.
    """
    try:
        result = json.loads(raw)["chart"]["result"][0]
        events = (result.get("events") or {}).get("splits") or {}
        offset = int(result["meta"].get("gmtoffset", 0))
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise FetchError(f"yahoo splits: unexpected payload ({exc})") from exc
    if not events:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([], name="date"))
    dates, ratios = [], []
    for ev in events.values():
        num, den = float(ev.get("numerator") or 0), float(ev.get("denominator") or 0)
        if num > 0 and den > 0:
            dates.append(pd.to_datetime(int(ev["date"]) + offset, unit="s").normalize())
            ratios.append(num / den)
    return pd.Series(ratios, index=pd.DatetimeIndex(dates, name="date"), dtype=float).sort_index()


def fetch_daily_with_splits(store: RawStore, symbol: str) -> tuple[pd.DataFrame, pd.Series]:
    name = f"yahoo_{symbol.replace('^', 'IDX_')}.json"
    raw = store.get(
        name,
        CHART_URL.format(symbol=quote(symbol)),
        headers=HEADERS,
        params={"period1": 0, "period2": 9_999_999_999, "interval": "1d", "events": "div,split"},
    )
    return parse_chart(raw, symbol), parse_splits(raw)
