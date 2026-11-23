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

# Market benchmark whose calendar defines real trading days (a stock bar on a
# day the benchmark has no bar is a carried-forward holiday bar).
MARKET_BENCH = {"TW": "^TWII", "US": "^NDX"}

# Outcomes with these statuses are final: kept as first computed, never rebuilt
# (a later failed fetch, a watchlist removal or a data revision cannot erase or
# change a scored forecast).
FINAL_STATUSES = {"scored", "gap", "data_error"}

# model_id values that denote the same model. Empty: the alias used briefly on
# 2026-11-23 covered identical CODE, but the 18 Taiwan rows it covered were
# produced before the holiday-bar cleaning existed (different data pipeline),
# so "same model" did not hold. The record restarts with the current id.
MODEL_ID_ALIASES: dict[str, str] = {}

STR_COLS = {"origin_date": str, "target_date": str, "symbol": str, "market": str, "level": str,
            "model_id": str, "engine_version": str, "issued_at": str, "status": str}

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
    """Fingerprint of what produces a stock forecast: the source of the
    forecasting functions (including the shared HAR fitting code and the light
    rule) and the stock config. Backtest-only or reporting changes do not
    change it; any change to how a forecast is made does."""
    import inspect

    from . import light, short_risk, stocks, tw_calendar
    parts = [stocks.drop_stale_runs, stocks.daily_frame, stocks.walk_forward_var, stocks.current_risk,
             stocks.analyze_stock, short_risk.design, short_risk.fit_var, short_risk.VarModel, short_risk._ols,
             light.level_for, tw_calendar.clean, tw_calendar.market_open_days]
    blob = "".join(inspect.getsource(f) for f in parts).encode()
    # Module-level constants the forecast depends on (not part of any function's source).
    blob += repr((stocks.HAR_FEATURES, sorted(short_risk.LOGGED))).encode()
    blob += json.dumps(asdict(stock_cfg), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


def bar_is_final(market: str, origin_date: str, now_utc: datetime) -> bool:
    tz, cutoff = MARKET_CLOSE[market]
    local = now_utc.astimezone(ZoneInfo(tz))
    d = pd.Timestamp(origin_date).date()
    if d < local.date():
        return True
    return d == local.date() and local.time() >= cutoff


def market_days(prices: dict[str, pd.DataFrame]) -> dict[str, set[str] | None]:
    """Real trading days per market from its benchmark (no bar or an unchanged
    close = market closed). None when the benchmark is unavailable."""
    out: dict[str, set[str] | None] = {}
    for m, b in MARKET_BENCH.items():
        px = prices.get(b)
        if px is None or px["close"].dropna().empty:
            out[m] = None
            continue
        c = px["close"].dropna()
        out[m] = set(c.index[~(c.diff() == 0)].strftime("%Y-%m-%d"))
    return out


def forecast_rows(stock_rows: list[dict], issued_at: str, now_utc: datetime, engine_version: str,
                  mid: str, non_trading: dict[str, set[str]] | None = None,
                  open_days: dict[str, set[str] | None] | None = None) -> list[dict]:
    out = []
    for r in stock_rows:
        if r.get("stale") or r.get("har_var") is None:
            continue
        if open_days is not None and open_days.get(r["market"]) is None:
            log.warning("ledger: %s benchmark unavailable, forecast for %s not logged", r["market"], r["symbol"])
            continue
        days = (open_days or {}).get(r["market"])
        if days is not None and r["last_date"] not in days:
            log.warning("ledger: %s bar %s is not a trading day of %s, forecast not logged",
                        r["symbol"], r["last_date"], MARKET_BENCH[r["market"]])
            continue
        if r.get("model_last_date") and r["model_last_date"] != r["last_date"]:
            # The model's data end earlier (stale run removed, outlier dropped):
            # the forecast is not for the day after last_date.
            log.warning("ledger: %s model data end %s != last bar %s, forecast not logged",
                        r["symbol"], r["model_last_date"], r["last_date"])
            continue
        if r["last_date"] in (non_trading or {}).get(r["symbol"], set()):
            log.warning("ledger: %s bar %s is not an exchange trading day, forecast not logged", r["symbol"], r["last_date"])
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


def append_ledger(path: Path, rows: list[dict], columns: list[str] = LEDGER_COLUMNS,
                  key: tuple[str, ...] = ("symbol", "origin_date")) -> int:
    """Append rows whose key is new. Existing bytes are never rewritten: the new
    file must start with the old file verbatim."""
    old = _read_text(path)
    keys = set()
    if old:
        rdr = csv.DictReader(io.StringIO(old))
        if rdr.fieldnames != columns:
            raise ValueError(f"ledger header mismatch: {rdr.fieldnames}")
        keys = {tuple(x[k] for k in key) for x in rdr}
    add = []
    for r in rows:
        k = tuple(r[c] for c in key)
        if k not in keys:
            keys.add(k)
            add.append(r)
    if not add:
        return 0
    buf = io.StringIO()
    w = csv.DictWriter(buf, columns, lineterminator="\n")
    if not old:
        w.writeheader()
    elif not old.endswith("\n"):
        raise ValueError("ledger does not end with a newline; refusing to append")
    w.writerows(add)
    _atomic_write(path, old + buf.getvalue())
    # Re-read: the file on disk must still start with the previous bytes
    # (guards against a concurrent writer; the workflow also checks the
    # committed file against the previous commit before pushing).
    if not path.read_text().startswith(old):
        raise ValueError("ledger append check failed: existing rows changed")
    return len(add)


def read_ledger(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=LEDGER_COLUMNS)
    return pd.read_csv(path, dtype={k: v for k, v in STR_COLS.items() if k in LEDGER_COLUMNS})


# ----------------------------------------------------------- reconciliation
def evaluate(ledger: pd.DataFrame, prices: dict[str, pd.DataFrame], markets: tuple[str, ...],
             cfg: ReviewConfig, non_trading: dict[str, set[str]] | None = None,
             open_days: dict[str, set[str] | None] | None = None, skip: set | None = None,
             now_utc: datetime | None = None) -> pd.DataFrame:
    """Match each forecast of `markets` with the stock's next real bar.
    Bars on days the market benchmark did not trade, or that the second-source
    check flags as non-trading, are skipped. Keys in `skip` (already final) are
    not re-evaluated."""
    non_trading = non_trading or {}
    check_days = open_days is not None   # None = no calendar filter (tests); dict = filter
    open_days = open_days or {}
    skip = skip or set()
    recs = []
    for _, f in ledger[ledger["market"].isin(markets)].iterrows():
        if (f["symbol"], f["origin_date"]) in skip:
            continue
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
        bad = non_trading.get(f["symbol"])
        if bad:
            after = after[~after.index.strftime("%Y-%m-%d").isin(list(bad))]
        days = open_days.get(f["market"])
        if check_days and days is None:
            rec["status"] = "pending"  # benchmark unavailable: no trading-day evidence, do not score
            recs.append(rec)
            continue
        if days is not None and len(after):
            # Only judge against bars the benchmark confirms; a bar after the
            # benchmark's last bar waits until the benchmark catches up.
            after = after[after.index.strftime("%Y-%m-%d").isin(list(days))]
        if after.empty:
            rec["status"] = "pending"
            recs.append(rec)
            continue
        t = after.index[0]
        if now_utc is not None and not bar_is_final(f["market"], str(t.date()), now_utc):
            rec["status"] = "pending"  # target bar still trading: never score (and freeze) a partial bar
            recs.append(rec)
            continue
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


def read_outcomes(path: Path) -> pd.DataFrame:
    """All columns as text (empty fields stay ""), so frozen rows are written
    back byte-identical; numbers are converted where they are used."""
    if not path.exists():
        return pd.DataFrame(columns=OUTCOME_COLUMNS)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def final_keys(old: pd.DataFrame) -> set:
    f = old[old["status"].isin(FINAL_STATUSES)]
    return set(zip(f["symbol"], f["origin_date"]))


def merge_outcomes(path: Path, fresh: pd.DataFrame, markets: tuple[str, ...]) -> pd.DataFrame:
    """Rebuild the non-final outcomes of `markets`; keep final outcomes and the
    other markets' rows exactly as they were."""
    old = read_outcomes(path)
    keep = old[~old["market"].isin(markets) | old["status"].isin(FINAL_STATUSES)]
    out = pd.concat([keep, fresh], ignore_index=True) if len(keep) else fresh
    out = out.sort_values(["origin_date", "market", "symbol"], kind="stable").reset_index(drop=True)
    _atomic_write(path, out.to_csv(index=False, lineterminator="\n"))
    return out


def _clustered_rate(x: np.ndarray, dates: np.ndarray, z: float, lag: int = 5) -> tuple[float, float, float]:
    """Mean of x with a standard error robust to both kinds of dependence:
    names breaching on the same day (deviations are summed per date) and
    breaches clustering over consecutive days (Newey-West, Bartlett weights,
    `lag` trading days, over the date-ordered daily sums). Clustering by date
    alone (the rule until 2026-11-23, before any outcome existed) ignored the
    second and was too narrow."""
    m = float(x.mean())
    d = pd.Series(x - m).groupby(dates).sum().sort_index().to_numpy()
    S = float((d ** 2).sum())
    for L in range(1, min(lag, len(d) - 1) + 1):
        S += 2 * (1 - L / (lag + 1)) * float((d[L:] * d[:-L]).sum())
    se = sqrt(max(S, 0.0)) / len(x)
    return m, m - z * se, m + z * se


def _too_many_test(x: np.ndarray, dates: np.ndarray, p0: float, lag: int = 5) -> tuple[float, float]:
    """One-sided z-test of "breach rate > p0" with a standard error computed
    from deviations from p0 (not from the sample rate), summed per date and
    Newey-West over dates, floored at the independent-binomial SE. Simulated
    false-positive rate <= 7.2% at a nominal 5% for 60-250 dates x 10-18 names
    with strong co-movement and persistence."""
    from statistics import NormalDist
    d = pd.Series(x - p0).groupby(dates).sum().sort_index().to_numpy()
    S = float((d ** 2).sum())
    for L in range(1, min(lag, len(d) - 1) + 1):
        S += 2 * (1 - L / (lag + 1)) * float((d[L:] * d[:-L]).sum())
    se = max(sqrt(max(S, 0.0)) / len(x), sqrt(p0 * (1 - p0) / len(x)))
    z = (float(x.mean()) - p0) / se
    return z, 1 - NormalDist().cdf(z)


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
    zt, pt = _too_many_test(br, dates, cfg.var_level)
    out.update(too_many_z=zt, too_many_p=pt)
    vr, vlo, vhi = _clustered_rate(s["var_ratio"].astype(float).to_numpy(), dates, z)
    out.update(breach_rate=rate, breach_ci=[lo, hi], var_ratio=vr, var_ratio_ci=[vlo, vhi])
    # HAR vs EWMA: per-date mean QLIKE difference, Newey-West t (positive => HAR better).
    by_d = s.groupby("target_date")[["qlike_ewma", "qlike_har"]].mean()
    out["qlike_har"] = float(s["qlike_har"].mean())
    out["qlike_ewma"] = float(s["qlike_ewma"].mean())
    out["dm_t_vs_ewma"] = diebold_mariano(by_d["qlike_ewma"].to_numpy(), by_d["qlike_har"].to_numpy(), 1)
    # One-sided by design (methodology section 14, 2026-11-23 round 5): "too many
    # breaches" is tested; "too few" is NOT, because no tested method controls
    # its false-positive rate when names breach together (simulated 6-27% at a
    # nominal 5%). The interval above is descriptive only.
    if n_dates < cfg.min_dates_pooled:
        out["verdict"] = "insufficient"
    elif pt < 0.05:
        out["verdict"] = "too_many"     # VaR too aggressive
    else:
        out["verdict"] = "not_rejected"
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
              as_of: str, current_model: str | None = None) -> dict:
    """Verdicts use only forecasts of the current model (after aliases); rows of
    other models are counted separately, so a model change starts from zero."""
    others: dict[str, int] = {}
    if current_model is not None and len(ledger):
        canon = ledger["model_id"].map(lambda v: MODEL_ID_ALIASES.get(v, v))
        others = {k: int(v) for k, v in canon[canon != current_model].value_counts().items()}
        ledger = ledger[canon == current_model]
        oc = outcomes["model_id"].map(lambda v: MODEL_ID_ALIASES.get(v, v))
        outcomes = outcomes[oc == current_model]
    sc = outcomes[outcomes["status"] == "scored"].copy()
    if len(sc):
        sc["breach"] = sc["breach"].map(lambda v: v in (True, "True", 1, "1"))
        for c in ("ret", "var95", "har_var", "ewma_var", "qlike_har", "qlike_ewma", "var_ratio"):
            sc[c] = pd.to_numeric(sc[c], errors="coerce")
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
            "current_model": current_model, "model_id_aliases": MODEL_ID_ALIASES,
            "other_models": others}


def non_trading_days(path: Path) -> dict[str, set[str]]:
    """Yahoo bars on days the exchange shows no trade, from data/official_check.json."""
    try:
        d = json.loads(Path(path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    return {s: set(v.get("extra") or []) for s, v in d.get("stocks", {}).items() if v.get("extra")}


def update(out_dir: Path, stock_rows: list[dict], prices: dict[str, pd.DataFrame], markets: tuple[str, ...],
           issued_at: str, now_utc: datetime, engine_version: str, stock_cfg, all_rows: list[dict] | None = None,
           cfg: ReviewConfig | None = None) -> dict:
    """Log today's forecasts for `markets`, reconcile them and write the review."""
    cfg = cfg or ReviewConfig()
    out_dir = Path(out_dir)
    lp = out_dir / "forecasts" / "stocks_ledger.csv"
    nt = non_trading_days(out_dir / "official_check.json")
    od = market_days(prices)
    mid = model_id(stock_cfg)
    added = append_ledger(lp, forecast_rows(stock_rows, issued_at, now_utc, engine_version, mid, nt, od))
    ledger = read_ledger(lp)
    op = out_dir / "forecasts" / "stocks_outcomes.csv"
    frozen = final_keys(read_outcomes(op))
    outcomes = merge_outcomes(op, evaluate(ledger, prices, markets, cfg, nt, od, frozen, now_utc), markets)
    review = summarize(outcomes, ledger, all_rows if all_rows is not None else stock_rows, cfg, issued_at, mid)
    review["last_run"] = {"markets": list(markets), "forecasts_added": added}
    from .export import clean  # local import: export imports heavy modules
    _atomic_write(out_dir / "forecast_review.json", json.dumps(clean(review), indent=1, allow_nan=False) + "\n")
    log.info("ledger %s: +%d forecasts (total %d); scored %d", "/".join(markets), added, len(ledger),
             int((outcomes["status"] == "scored").sum()))
    return review
