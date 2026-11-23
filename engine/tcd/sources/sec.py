"""SEC EDGAR XBRL companyfacts.

SEC fair-access policy requires a descriptive User-Agent and < 10 req/s.
Set SEC_USER_AGENT (e.g. "Org Name contact@org.example") in CI.
"""

from __future__ import annotations

import json
import time

import pandas as pd

from ..config import SEC_FORMS, Company
from .http import FetchError
from .store import RawStore

FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


def fetch_companyfacts(store: RawStore, company: Company, user_agent: str, pause_s: float = 0.25) -> dict:
    raw = store.get(
        f"sec_{company.ticker}.json",
        FACTS_URL.format(cik=company.cik),
        headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
    )
    if not store.offline:
        time.sleep(pause_s)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FetchError(f"sec {company.ticker}: invalid JSON ({exc})") from exc


def extract_facts(companyfacts: dict, tags: tuple[str, ...], unit: str = "USD") -> pd.DataFrame:
    """Flatten duration facts for the given tags.

    Returns columns: start, end, val, filed, form, tag, priority (0 = preferred).
    Instant facts (no start date) are ignored.
    """
    gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    rows: list[dict] = []
    for priority, tag in enumerate(tags):
        for item in gaap.get(tag, {}).get("units", {}).get(unit, []):
            if item.get("form") not in SEC_FORMS or "start" not in item:
                continue
            rows.append(
                {
                    "start": item["start"],
                    "end": item["end"],
                    "val": item["val"],
                    "filed": item["filed"],
                    "form": item["form"],
                    "tag": tag,
                    "priority": priority,
                }
            )
    cols = ["start", "end", "val", "filed", "form", "tag", "priority"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows, columns=cols)
    for c in ("start", "end", "filed"):
        df[c] = pd.to_datetime(df[c])
    df["val"] = df["val"].astype(float)
    return df


def extract_share_facts(companyfacts: dict, tags: tuple[str, ...]) -> pd.DataFrame:
    """Share-count facts (duration or instant). Columns: end, val, filed, priority."""
    gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    rows = []
    for priority, tag in enumerate(tags):
        for item in gaap.get(tag, {}).get("units", {}).get("shares", []):
            if item.get("form") not in SEC_FORMS or not item.get("val"):
                continue
            rows.append({"end": item["end"], "val": float(item["val"]), "filed": item["filed"], "priority": priority})
    df = pd.DataFrame(rows, columns=["end", "val", "filed", "priority"])
    for c in ("end", "filed"):
        df[c] = pd.to_datetime(df[c])
    return df
