"""Synthetic but structurally realistic raw data (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tcd.fetch import RawData  # noqa: E402


def _daily(start: str, end: str, rng: np.random.Generator, mu=0.0004, sd=0.012, p0=100.0) -> pd.Series:
    idx = pd.bdate_range(start, end)
    r = rng.normal(mu, sd, len(idx))
    return pd.Series(p0 * np.exp(np.cumsum(r)), index=idx)


def _sec_facts(rng: np.random.Generator, first_year: int, last_end: pd.Timestamp, base: float) -> dict[str, pd.DataFrame]:
    """Calendar fiscal year. 10-Q: 3M + YTD facts. 10-K: FY fact. Filed 35d after period end."""
    out = {}
    for metric, scale in (("capex", 0.1), ("revenue", 1.0), ("net_income", 0.2)):
        rows = []
        for y in range(first_year, last_end.year + 1):
            fy_start = pd.Timestamp(f"{y}-01-01")
            q_vals = base * scale * (1 + 0.02 * (y - first_year)) * rng.uniform(0.9, 1.1, 4)
            ytd = 0.0
            for q in range(4):
                q_start = fy_start + pd.DateOffset(months=3 * q)
                q_end = q_start + pd.offsets.QuarterEnd(0)
                if q_end > last_end:
                    break
                ytd += q_vals[q]
                filed = q_end + pd.Timedelta(days=35)
                if q < 3:
                    rows.append({"start": q_start, "end": q_end, "val": q_vals[q], "filed": filed, "form": "10-Q", "tag": "T", "priority": 0})
                    if q > 0:
                        rows.append({"start": fy_start, "end": q_end, "val": ytd, "filed": filed, "form": "10-Q", "tag": "T", "priority": 0})
                else:
                    rows.append({"start": fy_start, "end": q_end, "val": ytd, "filed": filed + pd.Timedelta(days=20), "form": "10-K", "tag": "T", "priority": 0})
        out[metric] = pd.DataFrame(rows)
    return out


def make_raw(seed: int = 7, end: str = "2026-11-20") -> RawData:
    rng = np.random.default_rng(seed)
    end_ts = pd.Timestamp(end)
    ndx = _daily("1985-10-01", end, rng)
    xlk_s = _daily("1998-12-22", end, rng)
    vix = pd.Series(np.clip(15 + np.cumsum(rng.normal(0, 0.8, len(pd.bdate_range("1990-01-02", end)))) * 0.05 + rng.normal(0, 4, len(pd.bdate_range("1990-01-02", end))), 9, 80),
                    index=pd.bdate_range("1990-01-02", end))
    q_idx = pd.date_range("1947-01-01", end_ts - pd.DateOffset(months=4), freq="QS")
    fred = {
        "tbill_3m": pd.Series(np.clip(rng.normal(3, 1, len(pd.bdate_range("1954-01-04", end))), 0, 10), index=pd.bdate_range("1954-01-04", end)),
        "it_invest": pd.Series(np.linspace(2, 1800, len(q_idx)) * rng.uniform(0.95, 1.05, len(q_idx)), index=q_idx),
        "gdp": pd.Series(np.linspace(240, 33000, len(q_idx)), index=q_idx),
        "corp_profits": pd.Series(np.linspace(20, 4300, len(q_idx)) * rng.uniform(0.9, 1.1, len(q_idx)), index=q_idx),
    }
    fred["vix_fred"] = vix
    sec = {f"C{i}": _sec_facts(rng, 2009 + i, end_ts, 100.0 * (i + 1)) for i in range(5)}

    # Per-company prices (Yahoo-style: retroactively split-adjusted), splits and
    # share-count facts reported on the raw (pre-split) basis.
    prices, splits, shares = {}, {}, {}
    for i, t in enumerate(sec):
        raw_px = _daily(f"{2008 + i}-01-02", end, rng, p0=50.0 * (i + 1))
        sp = pd.Series([4.0], index=pd.DatetimeIndex(["2018-06-15"])) if i == 0 else pd.Series(dtype=float, index=pd.DatetimeIndex([]))
        rows = []
        for q_end in pd.date_range(f"{2009 + i}-03-31", end_ts, freq="QE"):
            factor_before = float(sp[sp.index <= q_end].prod()) if len(sp) else 1.0
            rows.append({"end": q_end, "val": 1e9 * (i + 1) * factor_before, "filed": q_end + pd.Timedelta(days=35), "priority": 0})
        sh = pd.DataFrame(rows)
        shares[t] = sh[sh["filed"] <= end_ts].reset_index(drop=True)
        adj = raw_px.copy()
        for d, r in sp.items():
            adj[adj.index < d] /= r
        prices[t], splits[t] = adj, sp
    return RawData(
        ndx=pd.DataFrame({"close": ndx, "adjclose": ndx}),
        xlk=pd.DataFrame({"close": xlk_s, "adjclose": xlk_s}),
        vix=vix,
        fred=fred,
        sec_facts=sec,
        manifest={},
        prices=prices,
        splits=splits,
        shares=shares,
    )


def truncate(raw: RawData, cutoff: str) -> RawData:
    """What a run on `cutoff` could have seen."""
    c = pd.Timestamp(cutoff)
    return RawData(
        ndx=raw.ndx[raw.ndx.index <= c],
        xlk=raw.xlk[raw.xlk.index <= c],
        vix=raw.vix[raw.vix.index <= c],
        fred={k: v[v.index <= c] for k, v in raw.fred.items()},
        sec_facts={t: {m: f[f["filed"] <= c] for m, f in fs.items()} for t, fs in raw.sec_facts.items()},
        manifest={},
        # A run on `cutoff` sees prices on that day's split basis: undo later splits.
        prices={t: px[px.index <= c] * float(raw.splits[t][raw.splits[t].index > c].prod() if len(raw.splits[t]) else 1.0)
                for t, px in raw.prices.items()},
        splits={t: sp[sp.index <= c] for t, sp in raw.splits.items()},
        shares={t: sh[sh["filed"] <= c] for t, sh in raw.shares.items()},
    )


@pytest.fixture(scope="session")
def raw() -> RawData:
    return make_raw()
