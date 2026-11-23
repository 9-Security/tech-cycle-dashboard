"""Daily closes from Nasdaq's public quote API (second source for US stocks).

GET https://api.nasdaq.com/api/quote/{SYMBOL}/historical
    ?assetclass=stocks&fromdate=YYYY-MM-DD&todate=YYYY-MM-DD&limit=N

Covers NYSE- and Nasdaq-listed names (consolidated closes). Dates come as
MM/DD/YYYY and closes as "$101.19". The API rejects requests without a
browser-style User-Agent; a generic one is used (no contact details).
"""

from __future__ import annotations

import json
import re

import pandas as pd

from .http import FetchError
from .store import RawStore

URL = "https://api.nasdaq.com/api/quote/{symbol}/historical"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; tech-cycle-dashboard research)", "Accept": "application/json"}


def _num(s) -> float | None:
    t = re.sub(r"[^\d.\-]", "", str(s))
    try:
        return float(t) if t not in ("", "-", ".") else None
    except ValueError:
        return None


def parse(raw: bytes, symbol: str) -> pd.Series:
    """Date -> close. Raises FetchError on an error payload."""
    try:
        p = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FetchError(f"nasdaq {symbol}: not JSON ({exc})") from exc
    data = p.get("data") or {}
    rows = ((data.get("tradesTable") or {}).get("rows")) if data else None
    if rows is None:
        msg = (p.get("status") or {}).get("bCodeMessage") or (p.get("status") or {}).get("rCode")
        raise FetchError(f"nasdaq {symbol}: no data ({msg})")
    out = {}
    for r in rows:
        try:
            d = pd.to_datetime(r["date"], format="%m/%d/%Y")
        except (KeyError, ValueError) as exc:
            raise FetchError(f"nasdaq {symbol}: bad row {r!r}") from exc
        out[d] = _num(r.get("close"))
    return pd.Series(out, dtype=object).sort_index()


def fetch_range(store: RawStore, symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    raw = store.get(f"nasdaq_{symbol}_{start:%Y%m%d}_{end:%Y%m%d}.json", URL.format(symbol=symbol), headers=HEADERS,
                    params={"assetclass": "stocks", "fromdate": f"{start:%Y-%m-%d}", "todate": f"{end:%Y-%m-%d}",
                            "limit": 200})
    return parse(raw, symbol)
