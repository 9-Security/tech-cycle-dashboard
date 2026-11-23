"""Cross-check Yahoo daily closes against a second source.

Taiwan: TWSE / TPEx official closes. US: Nasdaq's public quote API
(consolidated closes for NYSE and Nasdaq names).

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

from .sources import nasdaq, twofficial
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


def _with_retry(fetch, store: RawStore, cfg: OfficialConfig):
    err = None
    for attempt in range(2):
        try:
            return fetch(), None
        except (FetchError, ValueError) as exc:  # throttled (HTTP 307/429) or bad payload
            err = str(exc)
            if store.offline or attempt:
                break
            time.sleep(cfg.backoff_s)
    return None, err


def _fetch_tw(s: str, last: pd.Timestamp, store: RawStore, cfg: OfficialConfig, pace) -> tuple[pd.Series | None, str | None]:
    cur = last.normalize().replace(day=1)
    parts = []
    for m in [cur - pd.DateOffset(months=k) for k in range(cfg.months - 1, -1, -1)]:
        pace()
        part, err = _with_retry(lambda: twofficial.fetch_month(store, s, m), store, cfg)
        if err:
            return None, err
        parts.append(part)
    off = pd.concat(parts) if parts else pd.Series(dtype=object)
    return off[~off.index.duplicated(keep="last")].sort_index(), None


def _fetch_us(s: str, last: pd.Timestamp, store: RawStore, cfg: OfficialConfig, pace) -> tuple[pd.Series | None, str | None]:
    start = last.normalize().replace(day=1) - pd.DateOffset(months=cfg.months - 1)
    pace()
    return _with_retry(lambda: nasdaq.fetch_range(store, s, start, last.normalize()), store, cfg)


VENUES = {"TW": lambda s: twofficial.venue(s), "US": lambda s: "Nasdaq"}
FETCH = {"TW": _fetch_tw, "US": _fetch_us}


def run(prices: dict[str, pd.DataFrame], watchlist: dict, store: RawStore, as_of: str,
        cfg: OfficialConfig | None = None, markets: tuple[str, ...] = ("US", "TW")) -> dict:
    """Second-source close check for the watchlist names of `markets`:
    Taiwan vs TWSE / TPEx (official), US vs Nasdaq's quote API."""
    cfg = cfg or OfficialConfig()
    stocks = {}
    state = {"first": True}

    def pace():
        if not state["first"] and not store.offline:
            time.sleep(cfg.pause_s)
        state["first"] = False

    for spec in watchlist["stocks"]:
        s, mk = spec["symbol"], spec["market"]
        if mk not in markets or VENUES[mk](s) is None:
            continue
        px = prices.get(s)
        if px is None:
            stocks[s] = {"market": mk, "status": "unavailable", "reason": "no Yahoo prices"}
            continue
        off, err = FETCH[mk](s, px["close"].dropna().index[-1], store, cfg, pace)
        if err:
            stocks[s] = {"market": mk, "venue": VENUES[mk](s), "status": "unavailable", "reason": err[:200]}
            log.warning("second-source check %s: %s", s, err)
            continue
        stocks[s] = {"market": mk, "venue": VENUES[mk](s), **compare(px["close"], off, cfg)}
    return {"as_of": as_of, "settings": asdict(cfg), "stocks": stocks, "updated": {m: as_of for m in markets},
            "source": {"TWSE": twofficial.TWSE_URL, "TPEx": twofficial.TPEX_URL, "Nasdaq": nasdaq.URL}}


def merge(existing: dict | None, new: dict, markets: tuple[str, ...], watchlist: dict) -> dict:
    """Replace the rows of `markets`, keep the other markets' rows; summaries per market.

    A name whose check failed this run ("unavailable") keeps its last good
    result, marked stale, so an outage of the second source neither erases the
    comparison nor the non-trading days the forecast ledger relies on. A market
    stamp only advances when at least one of its names was actually checked."""
    old = (existing or {}).get("stocks", {})
    mk_of = {x["symbol"]: x["market"] for x in watchlist["stocks"]}
    stocks = {s: v for s, v in old.items() if mk_of.get(s, v.get("market")) not in markets}
    for s, v in new["stocks"].items():
        prev = old.get(s)
        if v["status"] == "unavailable" and prev and prev.get("status") != "unavailable":
            stocks[s] = {**prev, "stale": True, "last_error": v.get("reason")}
        else:
            stocks[s] = v
    order = [x["symbol"] for x in watchlist["stocks"] if x["symbol"] in stocks]
    stocks = {s: {**stocks[s], "market": mk_of.get(s, stocks[s].get("market"))} for s in order}
    by = {}
    for m in ("US", "TW"):
        st = [v["status"] for v in stocks.values() if v["market"] == m]
        if st:
            by[m] = {k: int(v) for k, v in pd.Series(st).value_counts().items()}
    updated = dict((existing or {}).get("updated", {}))
    for m in by:
        # Files written before per-market stamps: the other market was checked at the old as_of.
        if m not in markets and m not in updated and (existing or {}).get("as_of"):
            updated[m] = existing["as_of"]
    for m, stamp in new["updated"].items():
        if any(v.get("market") == m and v["status"] != "unavailable" for v in new["stocks"].values()):
            updated[m] = stamp
    return {**new, "stocks": stocks, "summary_by_market": by, "updated": updated,
            "summary": {k: int(v) for k, v in pd.Series([v["status"] for v in stocks.values()]).value_counts().items()} if stocks else {},
            "n": len(stocks)}
