"""Official daily closes from the Taiwan exchanges (read-only, public).

* TWSE (listed, Yahoo suffix .TW):  /rwd/zh/afterTrading/STOCK_DAY - one stock, one month.
* TPEx (OTC, Yahoo suffix .TWO):    /www/zh-tw/afterTrading/tradingStock - one stock, one month.

Both return ROC-calendar dates ("115/11/02" = 2026-11-02) and closes as
strings with thousands separators; "--" means no trade that day. The
exchanges throttle aggressive clients, so callers must pace requests.
"""

from __future__ import annotations

import json
import re

import pandas as pd

from .http import FetchError
from .store import RawStore

TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
TPEX_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"
HEADERS = {"Accept": "application/json"}
CLOSE_FIELD = "收盤價"
CLOSE_INDEX = 6  # position of the close in both layouts when no field list is given


def venue(symbol: str) -> str | None:
    if symbol.endswith(".TWO"):
        return "TPEx"
    if symbol.endswith(".TW"):
        return "TWSE"
    return None


def roc_date(s: str) -> pd.Timestamp:
    m = re.fullmatch(r"\s*(\d{2,3})/(\d{1,2})/(\d{1,2})\s*", s)
    if not m:
        raise ValueError(f"bad ROC date {s!r}")
    return pd.Timestamp(int(m.group(1)) + 1911, int(m.group(2)), int(m.group(3)))


def _num(s) -> float | None:
    t = re.sub(r"[^\d.\-]", "", str(s))
    if t in ("", "-", "--", ".") or set(t) <= {"-"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _rows(fields: list | None, data: list) -> pd.Series:
    i = fields.index(CLOSE_FIELD) if fields and CLOSE_FIELD in fields else CLOSE_INDEX
    out = {}
    for r in data:
        out[roc_date(r[0])] = _num(r[i]) if len(r) > i else None
    return pd.Series(out, dtype=object).sort_index()


def parse_twse(raw: bytes) -> pd.Series:
    """Date -> official close (None = no trade). Raises FetchError on an error payload."""
    try:
        p = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FetchError(f"twse: not JSON ({exc})") from exc
    if p.get("stat") != "OK":
        if "沒有符合" in str(p.get("stat", "")):  # "no matching data" (e.g. month before listing)
            return pd.Series(dtype=object)
        raise FetchError(f"twse: stat={p.get('stat')!r}")
    return _rows(p.get("fields"), p.get("data") or [])


def parse_tpex(raw: bytes) -> pd.Series:
    try:
        p = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FetchError(f"tpex: not JSON ({exc})") from exc
    tables = p.get("tables") or []
    if not tables:
        if str(p.get("stat", "ok")).lower() not in ("ok", ""):
            raise FetchError(f"tpex: stat={p.get('stat')!r}")
        return pd.Series(dtype=object)
    t = tables[0]
    return _rows(t.get("fields"), t.get("data") or [])


def fetch_month(store: RawStore, symbol: str, month: pd.Timestamp) -> pd.Series:
    code = symbol.split(".")[0]
    v = venue(symbol)
    if v == "TWSE":
        raw = store.get(f"twse_{code}_{month:%Y%m}.json", TWSE_URL, headers=HEADERS,
                        params={"date": f"{month:%Y%m}01", "stockNo": code, "response": "json"})
        return parse_twse(raw)
    if v == "TPEx":
        raw = store.get(f"tpex_{code}_{month:%Y%m}.json", TPEX_URL, headers=HEADERS,
                        params={"code": code, "date": f"{month:%Y/%m}/01", "response": "json"})
        return parse_tpex(raw)
    raise ValueError(f"not a Taiwan symbol: {symbol}")
