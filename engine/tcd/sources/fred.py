"""FRED public CSV endpoint (no API key required)."""

from __future__ import annotations

import io

import pandas as pd

from .http import FetchError
from .store import RawStore

CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"
# FRED's edge drops some custom User-Agents; the library default is accepted.
HEADERS: dict[str, str] = {}


def fetch_series(store: RawStore, series_id: str) -> pd.Series:
    raw = store.get(f"fred_{series_id}.csv", CSV_URL, headers=HEADERS, params={"id": series_id})
    return parse_csv(raw, series_id)


def parse_csv(raw: bytes, series_id: str) -> pd.Series:
    try:
        df = pd.read_csv(io.BytesIO(raw), na_values=["."])
    except Exception as exc:  # pandas raises several parser error types
        raise FetchError(f"fred {series_id}: cannot parse CSV ({exc})") from exc
    if df.shape[1] < 2 or series_id not in df.columns:
        raise FetchError(f"fred {series_id}: unexpected columns {list(df.columns)}")
    s = pd.Series(
        pd.to_numeric(df[series_id], errors="coerce").values,
        index=pd.DatetimeIndex(pd.to_datetime(df.iloc[:, 0]), name="date"),
        name=series_id,
    ).dropna()
    if s.empty:
        raise FetchError(f"fred {series_id}: no observations")
    return s.sort_index()
