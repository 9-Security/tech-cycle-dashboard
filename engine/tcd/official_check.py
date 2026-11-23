"""Cross-check Yahoo daily closes of Taiwan stocks against the exchanges.

Report only: the check never changes prices, the model or the ledger, and a
failure never blocks a refresh. For each Taiwan name it compares Yahoo's
(split-adjusted, not dividend-adjusted) close with the official close over
the current and previous calendar month:

  * mismatch      - both have the day, |Yahoo / official - 1| > tolerance;
  * missing       - official trade, no Yahoo bar;
  * extra         - Yahoo bar on a day the exchange shows no trade
                    (typically a carried-forward stale price);
  * not_yet       - Yahoo bar after the exchange's latest published day
                    (official data not out yet): informational only.

Status per stock: ok / warn (any mismatch, missing or extra) / unavailable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass

import pandas as pd

from .sources import twofficial
from .sources.http import FetchError
from .sources.store import RawStore

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class OfficialConfig:
    tolerance: float = 0.005   # 0.5%: well above tick-size rounding, well below a real move
    months: int = 2            # current + previous calendar month
    pause_s: float = 2.0       # between requests (the exchanges throttle bursts)
    backoff_s: float = 15.0    # one slow retry after a throttled / failed request
    max_listed: int = 10       # issues listed per category in the output


def compare(yahoo_close: pd.Series, official: pd.Series, cfg: OfficialConfig) -> dict:
    off = official.copy()
    off.index = pd.DatetimeIndex(off.index)
    traded = off[off.map(lambda v: v is not None)].astype(float)
    if off.empty:
        return {"status": "unavailable", "reason": "no official rows"}
    lo, hi = off.index.min(), off.index.max()
    y = yahoo_close.dropna()
    y_in = y[(y.index >= lo) & (y.index <= hi)]
    both = traded.index.intersection(y_in.index)
    rel = (y_in.loc[both] / traded.loc[both] - 1)
    bad = rel[rel.abs() > cfg.tolerance]
    missing = traded.index.difference(y_in.index)
    extra = y_in.index.difference(traded.index)
    not_yet = y[y.index > hi].index
    lst = lambda idx: [str(d.date()) for d in idx[: cfg.max_listed]]
    out = {
        "window": [str(lo.date()), str(hi.date())], "official_last": str(hi.date()),
        "compared": int(len(both)), "max_abs_diff": float(rel.abs().max()) if len(rel) else None,
        "mismatches": [{"date": str(d.date()), "yahoo": float(y_in.loc[d]), "official": float(traded.loc[d]),
                        "diff": float(rel.loc[d])} for d in bad.index[: cfg.max_listed]],
        "n_mismatch": int(len(bad)), "missing": lst(missing), "n_missing": int(len(missing)),
        "extra": [str(d.date()) for d in extra], "n_extra": int(len(extra)), "not_yet": lst(not_yet),
    }
    out["status"] = "warn" if (len(bad) or len(missing) or len(extra)) else "ok"
    return out


def run(prices: dict[str, pd.DataFrame], watchlist: dict, store: RawStore, as_of: str,
        cfg: OfficialConfig | None = None) -> dict:
    cfg = cfg or OfficialConfig()
    stocks, first = {}, True
    for spec in watchlist["stocks"]:
        s = spec["symbol"]
        if spec["market"] != "TW" or twofficial.venue(s) is None:
            continue
        px = prices.get(s)
        if px is None:
            stocks[s] = {"status": "unavailable", "reason": "no Yahoo prices"}
            continue
        last = px["close"].dropna().index[-1]
        cur = last.normalize().replace(day=1)
        months = [cur - pd.DateOffset(months=k) for k in range(cfg.months - 1, -1, -1)]
        parts, err = [], None
        for m in months:
            if not first and not store.offline:
                time.sleep(cfg.pause_s)
            first = False
            for attempt in range(2):
                try:
                    parts.append(twofficial.fetch_month(store, s, m))
                    err = None
                    break
                except (FetchError, ValueError) as exc:  # throttled (HTTP 307/429) or bad payload
                    err = str(exc)
                    if store.offline or attempt:
                        break
                    time.sleep(cfg.backoff_s)
            if err:
                break
        if err:
            stocks[s] = {"status": "unavailable", "reason": err[:200]}
            log.warning("official check %s: %s", s, err)
            continue
        off = pd.concat(parts) if parts else pd.Series(dtype=object)
        off = off[~off.index.duplicated(keep="last")].sort_index()
        stocks[s] = {"venue": twofficial.venue(s), **compare(px["close"], off, cfg)}
    counts = pd.Series([v["status"] for v in stocks.values()]).value_counts().to_dict() if stocks else {}
    return {"as_of": as_of, "settings": asdict(cfg), "stocks": stocks,
            "summary": {k: int(v) for k, v in counts.items()}, "n": len(stocks),
            "source": {"TWSE": twofficial.TWSE_URL, "TPEx": twofficial.TPEX_URL}}
