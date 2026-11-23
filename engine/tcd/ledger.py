"""Live forecast ledger and reconciliation for the per-stock risk monitor.

The walk-forward backtest in `stocks.py` is a *pseudo* out-of-sample check:
it re-runs today's model over the past. This module keeps the *real* record:

  * `data/forecasts/stocks_ledger.csv` - append-only. Every refresh appends
    each freshly analysed stock's forecast for the next trading day (VaR,
    HAR and EWMA variance, risk light), keyed by (symbol, origin_date). The
    first forecast written for a key wins; later runs never change or
    delete a row (checked byte-for-byte before every write). Each day's
    rows are committed to git before the outcome exists, so the commit
    history proves no hindsight.
  * `data/forecasts/stocks_outcomes.csv` - regenerated: each ledger row
    matched to the stock's next bar (realized log return, VaR breach,
    QLIKE of HAR and EWMA, r^2 / forecast variance).
  * `data/forecast_review.json` - summary per market and per stock, with
    minimum-sample gates (pre-registered in docs/methodology.md section 14):
    no verdict is given before the gates are met.

Forecasts are only logged when the last bar is final (the market's local
close plus a buffer has passed), so a manual run during trading hours
cannot log a forecast built on a partial bar. Nothing here feeds back into
the model: recalibration is a versioned, documented change, never automatic.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, time
from math import sqrt
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .short_risk import christoffersen, diebold_mariano, kupiec, qlike

log = logging.getLogger(__name__)

LEDGER_COLUMNS = ["origin_date", "symbol", "market", "issued_at", "var95", "har_var", "ewma_var",
                  "vol_1d_ann", "level", "engine_version", "model_id"]
OUTCOME_COLUMNS = ["origin_date", "symbol", "market", "target_date", "status", "ret", "var95", "breach",
                   "har_var", "ewma_var", "level", "qlike_har", "qlike_ewma", "var_ratio", "model_id"]

# Last bar is final once local time passes close + buffer.
MARKET_CLOSE = {"TW": ("Asia/Taipei", time(14, 30)),        # TWSE closes 13:30
                "US": ("America/New_York", time(16, 30))}   # NYSE / Nasdaq close 16:00


@dataclass(frozen=True)
class ReviewConfig:
    var_level: float = 0.05
    min_days_stock: int = 250       # per-stock verdict (Kupiec + Christoffersen)
    min_dates_pooled: int = 60      # pooled verdict per market
    rolling_dates: int = 60
    ci: float = 0.90
    tw_max_abs_logret: float = 0.25  # same data-error rule as the model
    max_gap_days: int = 10          # next bar further away than this: not scored (halt / data gap)


def model_id(stock_cfg) -> str:
    """Fingerprint of the stock model: source of stocks.py + its config."""
    src = (Path(__file__).with_name("stocks.py")).read_bytes()
    blob = src + json.dumps(asdict(stock_cfg), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def bar_is_final(market: str, origin_date: str, now_utc: datetime) -> bool:
    tz, cutoff = MARKET_CLOSE[market]
    local = now_utc.astimezone(ZoneInfo(tz))
    d = pd.Timestamp(origin_date).date()
    if d < local.date():
        return True
    return d == local.date() and local.time() >= cutoff


def forecast_rows(stock_rows: list[dict], issued_at: str, now_utc: datetime, engine_version: str,
                  mid: str) -> list[dict]:
    out = []
    for r in stock_rows:
        if r.get("stale") or r.get("har_var") is None:
            continue
        if not bar_is_final(r["market"], r["last_date"], now_utc):
            log.info("ledger: %s bar %s not final yet, forecast not logged", r["symbol"], r["last_date"])
            continue
        out.append({"origin_date": r["last_date"], "symbol": r["symbol"], "market": r["market"],
                    "issued_at": issued_at, "var95": f"{r['var95']:.8f}", "har_var": f"{r['har_var']:.10e}",
                    "ewma_var": f"{r['ewma_var']:.10e}", "vol_1d_ann": f"{r['vol_1d_ann']:.6f}",
                    "level": r["level"], "engine_version": engine_version, "model_id": mid})
    return out


def _read_text(path: Path) -> str:
    return path.read_text() if path.exists() else ""


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def append_ledger(path: Path, rows: list[dict]) -> int:
    """Append rows whose (symbol, origin_date) is new. Existing bytes are
    never rewritten: the new file must start with the old file verbatim."""
    old = _read_text(path)
    keys = set()
    if old:
        rdr = csv.DictReader(io.StringIO(old))
        if rdr.fieldnames != LEDGER_COLUMNS:
            raise ValueError(f"ledger header mismatch: {rdr.fieldnames}")
        keys = {(x["symbol"], x["origin_date"]) for x in rdr}
    add = []
    for r in rows:
        k = (r["symbol"], r["origin_date"])
        if k not in keys:
            keys.add(k)
            add.append(r)
    if not add:
        return 0
    buf = io.StringIO()
    w = csv.DictWriter(buf, LEDGER_COLUMNS, lineterminator="\n")
    if not old:
        w.writeheader()
    elif not old.endswith("\n"):
        raise ValueError("ledger does not end with a newline; refusing to append")
    w.writerows(add)
    new = old + buf.getvalue()
    assert new.startswith(old)
    _atomic_write(path, new)
    return len(add)


def read_ledger(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=LEDGER_COLUMNS)
    return pd.read_csv(path, dtype={"origin_date": str, "symbol": str, "market": str, "level": str,
                                    "model_id": str, "engine_version": str, "issued_at": str})


# ----------------------------------------------------------- reconciliation
def evaluate(ledger: pd.DataFrame, prices: dict[str, pd.DataFrame], markets: tuple[str, ...],
             cfg: ReviewConfig) -> pd.DataFrame:
    """Match each forecast of `markets` with the stock's next bar."""
    recs = []
    for _, f in ledger[ledger["market"].isin(markets)].iterrows():
        rec = {k: f[k] for k in ("origin_date", "symbol", "market", "var95", "har_var", "ewma_var", "level", "model_id")}
        rec.update(target_date=None, ret=None, breach=None, qlike_har=None, qlike_ewma=None, var_ratio=None)
        px = prices.get(f["symbol"])
        close = None if px is None else px["adjclose"].dropna()
        o = pd.Timestamp(f["origin_date"])
        if close is None or o not in close.index:
            rec["status"] = "no_price" if close is None else "origin_missing"
            recs.append(rec)
            continue
        after = close[close.index > o]
        if after.empty:
            rec["status"] = "pending"
            recs.append(rec)
            continue
        t = after.index[0]
        r = float(np.log(after.iloc[0] / close.loc[o]))
        rec["target_date"], rec["ret"] = str(t.date()), r
        if (t - o).days > cfg.max_gap_days:
            rec["status"] = "gap"
        elif f["market"] == "TW" and abs(r) > cfg.tw_max_abs_logret:
            rec["status"] = "data_error"
        else:
            hv, ev = float(f["har_var"]), float(f["ewma_var"])
            rec["status"] = "scored"
            rec["breach"] = bool(np.expm1(r) < -float(f["var95"]))
            rec["qlike_har"] = float(qlike(np.array([r * r]), np.array([hv]))[0])
            rec["qlike_ewma"] = float(qlike(np.array([r * r]), np.array([ev]))[0])
            rec["var_ratio"] = r * r / hv
        recs.append(rec)
    return pd.DataFrame(recs, columns=OUTCOME_COLUMNS)


def merge_outcomes(path: Path, fresh: pd.DataFrame, markets: tuple[str, ...]) -> pd.DataFrame:
    """Replace the outcomes of `markets`, keep those of other markets."""
    if path.exists():
        old = pd.read_csv(path, dtype={"origin_date": str, "target_date": str, "symbol": str})
        old = old[~old["market"].isin(markets)]
        out = pd.concat([old, fresh], ignore_index=True) if len(old) else fresh
    else:
        out = fresh
    out = out.sort_values(["origin_date", "market", "symbol"], kind="stable").reset_index(drop=True)
    _atomic_write(path, out.to_csv(index=False, lineterminator="\n"))
    return out


def _clustered_rate(x: np.ndarray, dates: np.ndarray, z: float) -> tuple[float, float, float]:
    """Mean of x with a standard error clustered by date (names breach on the
    same days, so they are not independent observations)."""
    m = float(x.mean())
    d = pd.Series(x - m).groupby(dates).sum().to_numpy()
    se = sqrt(float((d ** 2).sum())) / len(x)
    return m, m - z * se, m + z * se


def _pooled(s: pd.DataFrame, cfg: ReviewConfig) -> dict:
    z = {0.90: 1.6449, 0.95: 1.96}[cfg.ci]
    n_dates = int(s["target_date"].nunique())
    out = {"n": int(len(s)), "n_dates": n_dates, "breaches": int(s["breach"].sum()) if len(s) else 0,
           "first_date": s["target_date"].min() if len(s) else None,
           "last_date": s["target_date"].max() if len(s) else None}
    if not len(s):
        return {**out, "verdict": "insufficient"}
    br = s["breach"].astype(float).to_numpy()
    dates = s["target_date"].to_numpy()
    rate, lo, hi = _clustered_rate(br, dates, z)
    vr, vlo, vhi = _clustered_rate(s["var_ratio"].astype(float).to_numpy(), dates, z)
    out.update(breach_rate=rate, breach_ci=[lo, hi], var_ratio=vr, var_ratio_ci=[vlo, vhi])
    # HAR vs EWMA: per-date mean QLIKE difference, Newey-West t (positive => HAR better).
    by_d = s.groupby("target_date")[["qlike_ewma", "qlike_har"]].mean()
    out["qlike_har"] = float(s["qlike_har"].mean())
    out["qlike_ewma"] = float(s["qlike_ewma"].mean())
    out["dm_t_vs_ewma"] = diebold_mariano(by_d["qlike_ewma"].to_numpy(), by_d["qlike_har"].to_numpy(), 1)
    if n_dates < cfg.min_dates_pooled:
        out["verdict"] = "insufficient"
    elif hi < cfg.var_level:
        out["verdict"] = "too_few"      # VaR too conservative
    elif lo > cfg.var_level:
        out["verdict"] = "too_many"     # VaR too aggressive
    else:
        out["verdict"] = "consistent"
    last = sorted(s["target_date"].unique())[-cfg.rolling_dates:]
    r = s[s["target_date"].isin(last)]
    out["rolling"] = {"n_dates": len(last), "n": int(len(r)), "breaches": int(r["breach"].sum()),
                      "breach_rate": float(r["breach"].mean())}
    lv = {}
    for k, g in s.groupby("level"):
        lv[k] = {"n": int(len(g)), "realized_vol_ann": float(sqrt(float((g["ret"].astype(float) ** 2).mean()) * 252)),
                 "forecast_vol_ann": float(sqrt(float(g["har_var"].astype(float).mean()) * 252))}
    out["by_level"] = lv
    return out


def _per_stock(s: pd.DataFrame, cfg: ReviewConfig) -> dict:
    s = s.sort_values("target_date")
    br = s["breach"].astype(bool).to_numpy()
    out = {"n": int(len(s)), "breaches": int(br.sum()), "breach_rate": float(br.mean()) if len(br) else None,
           "kupiec_p": None, "christoffersen_p": None, "verdict": "insufficient"}
    if len(s) >= cfg.min_days_stock:
        k, c = kupiec(br, cfg.var_level), christoffersen(br)
        out.update(kupiec_p=k["p_value"], christoffersen_p=c["p_value"])
        out["verdict"] = ("consistent" if k["p_value"] >= 0.05 and c["p_value"] >= 0.05
                          else "coverage_rejected" if k["p_value"] < 0.05 else "breaches_cluster")
    return out


def summarize(outcomes: pd.DataFrame, ledger: pd.DataFrame, stock_rows: list[dict], cfg: ReviewConfig,
              as_of: str) -> dict:
    sc = outcomes[outcomes["status"] == "scored"].copy()
    if len(sc):
        sc["breach"] = sc["breach"].map(lambda v: v in (True, "True", 1, "1"))
    bt = {r["symbol"]: r.get("backtest", {}) for r in stock_rows}
    markets, stocks = {}, {}
    for m in ("US", "TW"):
        sm = sc[sc["market"] == m]
        lm = ledger[ledger["market"] == m]
        st = outcomes[outcomes["market"] == m]["status"].value_counts().to_dict()
        rates = [bt[x]["breach_rate"] for x in bt if bt[x].get("breach_rate") is not None
                 and any(r["symbol"] == x and r["market"] == m for r in stock_rows)]
        markets[m] = {**_pooled(sm, cfg), "logged": int(len(lm)),
                      "logged_since": lm["origin_date"].min() if len(lm) else None,
                      "status_counts": {k: int(v) for k, v in st.items()},
                      "backtest_breach_rate_mean": float(np.mean(rates)) if rates else None}
    for sym, g in sc.groupby("symbol"):
        stocks[sym] = {**_per_stock(g, cfg), "backtest_breach_rate": bt.get(sym, {}).get("breach_rate")}
    for sym in ledger["symbol"].unique():
        stocks.setdefault(sym, {**_per_stock(sc.iloc[0:0], cfg), "backtest_breach_rate": bt.get(sym, {}).get("breach_rate")})
    return {"as_of": as_of, "settings": asdict(cfg), "markets": markets, "stocks": stocks,
            "model_ids": sorted(ledger["model_id"].dropna().unique().tolist()) if len(ledger) else []}


def update(out_dir: Path, stock_rows: list[dict], prices: dict[str, pd.DataFrame], markets: tuple[str, ...],
           issued_at: str, now_utc: datetime, engine_version: str, stock_cfg, all_rows: list[dict] | None = None,
           cfg: ReviewConfig | None = None) -> dict:
    """Log today's forecasts for `markets`, reconcile them and write the review."""
    cfg = cfg or ReviewConfig()
    out_dir = Path(out_dir)
    lp = out_dir / "forecasts" / "stocks_ledger.csv"
    added = append_ledger(lp, forecast_rows(stock_rows, issued_at, now_utc, engine_version, model_id(stock_cfg)))
    ledger = read_ledger(lp)
    outcomes = merge_outcomes(out_dir / "forecasts" / "stocks_outcomes.csv", evaluate(ledger, prices, markets, cfg), markets)
    review = summarize(outcomes, ledger, all_rows if all_rows is not None else stock_rows, cfg, issued_at)
    review["last_run"] = {"markets": list(markets), "forecasts_added": added}
    from .export import clean  # local import: export imports heavy modules
    _atomic_write(out_dir / "forecast_review.json", json.dumps(clean(review), indent=1, allow_nan=False) + "\n")
    log.info("ledger %s: +%d forecasts (total %d); scored %d", "/".join(markets), added, len(ledger),
             int((outcomes["status"] == "scored").sum()))
    return review
