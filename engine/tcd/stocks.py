"""Per-stock risk monitoring (US mega caps + Taiwan AI supply chain).

Risk monitoring only - no buy/sell signals and no per-stock strategy
backtests (one stock's history is far too short to tune a strategy on).

For each stock:
  * next-day volatility from a log-HAR model on the stock's own daily
    returns (no VIX: there is no implied-vol index for most Taiwan names),
    with EWMA (RiskMetrics 0.94) as the baseline;
  * 1-day 95% VaR by filtered historical simulation, backtested
    walk-forward (annual refit, targets fully realized before each fit);
    "verified" only with >= 500 OOS days and Kupiec and Christoffersen
    p >= 0.05. Stock-specific robustness (fixed when first run on real data
    exposed numerical failures, not tuned on results): the HAR is fitted on
    the next-5-day average variance (single-day squared returns are often
    exactly zero for Taiwan stocks: price limits, thin trading), the daily
    term is floored at 5% of the 22-day average, and Taiwan returns beyond
    +/-25% (impossible under the +/-7%/10% exchange limits: unadjusted
    corporate actions or data errors) are dropped; runs of >= 5 consecutive
    unchanged closes are treated as stale/missing data (the source carries
    prices forward through halts and data gaps: up to 272 days for one
    stock) and removed, and rows whose variance target is zero are not
    used for fitting;
  * risk light on the same rule as the market light, against the stock's
    own history of 22-day realized volatility;
  * 1-month return, drawdown from the 52-week high, beta to its market
    benchmark (^NDX for US, ^TWII for Taiwan) over the last year;
  * US only: point-in-time SEC fundamentals (TTM revenue / net income and
    their year-on-year growth, trailing P/E, Capex / revenue, last filing).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from . import fundamentals as fx
from .light import level_for
from .short_risk import christoffersen, design, diebold_mariano, fit_var, kupiec, qlike
from .sources import yahoo
from .sources.http import FetchError
from .sources.store import RawStore

log = logging.getLogger(__name__)

HAR_FEATURES = ["rv_d", "rv_w", "rv_m"]
WATCHLIST = Path(__file__).resolve().parents[1] / "watchlist.json"
SEGMENTS = {"mega_cap", "foundry", "ic_design", "server_odm", "power", "thermal", "rails", "networking", "pcb", "packaging"}


@dataclass(frozen=True)
class StockConfig:
    lam: float = 0.94
    var_level: float = 0.05
    min_train_days: int = 1000
    rv_d_floor_frac: float = 0.05  # floor single-day r^2 at this fraction of the 22-day mean
    tw_max_abs_logret: float = 0.25  # Taiwan price limits are +/-10% (+/-7% before 2015)
    stale_run_days: int = 5  # consecutive unchanged closes treated as stale data
    min_oos_days: int = 500
    verify_p: float = 0.05
    log_floor: float = 1e-8
    var_floor: float = 1e-10
    chart_days: int = 252


def load_watchlist(path: Path = WATCHLIST) -> dict:
    wl = json.loads(Path(path).read_text())
    seen = set()
    for s in wl["stocks"]:
        if s["symbol"] in seen:
            raise ValueError(f"duplicate symbol {s['symbol']}")
        seen.add(s["symbol"])
        if s["market"] not in ("US", "TW"):
            raise ValueError(f"{s['symbol']}: market must be US or TW")
        if s["market"] == "US" and not s.get("cik"):
            raise ValueError(f"{s['symbol']}: US stocks need a cik")
        if s["segment"] not in SEGMENTS:
            raise ValueError(f"{s['symbol']}: unknown segment {s['segment']}")
    return wl


# ------------------------------------------------------------- daily model
def drop_stale_runs(r: pd.Series, min_run: int) -> pd.Series:
    """Remove runs of >= min_run consecutive zero returns (stale carried-forward prices)."""
    z = (r == 0)
    run_id = (z != z.shift()).cumsum()
    run_len = z.groupby(run_id).transform("sum")
    return r[~(z & (run_len >= min_run))]


def daily_frame(close: pd.Series, lam: float, max_abs_logret: float | None = None,
                rv_d_floor_frac: float = 0.05, stale_run_days: int = 5) -> pd.DataFrame:
    r = np.log(close.dropna()).diff().dropna()
    r = r[np.isfinite(r)]
    r = drop_stale_runs(r, stale_run_days)
    if max_abs_logret is not None:
        r = r[r.abs() <= max_abs_logret]
    df = pd.DataFrame({"r": r})
    r2 = r ** 2
    df["rv_w"], df["rv_m"] = r2.rolling(5).mean(), r2.rolling(22).mean()
    df["rv_d"] = np.maximum(r2, rv_d_floor_frac * df["rv_m"])
    ew = np.empty(len(df))
    ew[0] = r2.iloc[:22].mean()
    rr = r2.to_numpy()
    for i in range(1, len(df)):
        ew[i] = lam * ew[i - 1] + (1 - lam) * rr[i]
    df["ewma"] = ew
    df["y1"] = r2.shift(-1)
    df["y5"] = sum(r2.shift(-k) for k in range(1, 6)) / 5  # fitting target (robust to zero days)
    df["r_next"] = r.shift(-1)
    return df


def walk_forward_var(df: pd.DataFrame, cfg: StockConfig) -> pd.DataFrame:
    """OOS HAR variance + FHS quantile per day (annual refit)."""
    X = design(df, HAR_FEATURES, "log", cfg.log_floor)
    ok = ~np.isnan(X).any(axis=1)
    y = df["y5"].to_numpy(float)
    idx = df.index
    out = pd.DataFrame(index=idx, columns=["f_har", "q_har"], dtype=float)
    for Y in range(int(idx[0].year) + 1, int(idx[-1].year) + 1):
        known = (idx + pd.offsets.BDay(5)) <= pd.Timestamp(f"{Y - 1}-12-31")
        tr = ok & known & ~np.isnan(y) & (y > 0) & (df["rv_m"].to_numpy(float) > 0)
        te = (idx.year == Y) & ok
        if tr.sum() < cfg.min_train_days or not te.any():
            continue
        m = fit_var(X[tr], y[tr], HAR_FEATURES, "log", cfg.log_floor)
        out.loc[te, "f_har"] = m.predict(X[te], cfg.var_floor)
        z = df["r_next"].to_numpy(float)[tr] / np.sqrt(m.predict(X[tr], cfg.var_floor))
        out.loc[te, "q_har"] = float(np.nanquantile(z[np.isfinite(z)], cfg.var_level))
    return out


def backtest(df: pd.DataFrame, fc: pd.DataFrame, cfg: StockConfig) -> dict:
    ok = fc["f_har"].notna() & fc["q_har"].notna() & df["r_next"].notna() & (df["y1"] > 0)
    if ok.sum() == 0:
        return {"oos_days": 0, "verified": False, "reason": "insufficient history"}
    f = fc.loc[ok, "f_har"].to_numpy(float)
    q = fc.loc[ok, "q_har"].to_numpy(float)
    rn = df.loc[ok, "r_next"].to_numpy(float)
    br = rn < q * np.sqrt(f)
    k, c = kupiec(br, cfg.var_level), christoffersen(br)
    y = df.loc[ok, "y1"].to_numpy(float)
    ew = df.loc[ok, "ewma"].to_numpy(float)
    dm = diebold_mariano(qlike(y, ew), qlike(y, f), 5)
    n = int(ok.sum())
    verified = n >= cfg.min_oos_days and k["p_value"] >= cfg.verify_p and c["p_value"] >= cfg.verify_p
    reason = ("ok" if verified else "short history" if n < cfg.min_oos_days
              else "coverage rejected" if k["p_value"] < cfg.verify_p else "breaches cluster")
    return {"oos_days": n, "oos_start": str(df.index[ok][0].date()), "breach_rate": k["rate"],
            "kupiec_p": k["p_value"], "christoffersen_p": c["p_value"], "dm_t_vs_ewma": dm,
            "verified": bool(verified), "reason": reason}


def current_risk(df: pd.DataFrame, cfg: StockConfig) -> dict:
    X = design(df, HAR_FEATURES, "log", cfg.log_floor)
    ok = ~np.isnan(X).any(axis=1)
    y = df["y5"].to_numpy(float)
    tr = ok & ~np.isnan(y) & (y > 0) & (df["rv_m"].to_numpy(float) > 0) & ~np.isnan(df["r_next"].to_numpy(float))
    m = fit_var(X[tr], y[tr], HAR_FEATURES, "log", cfg.log_floor)
    fv = float(m.predict(X[-1:], cfg.var_floor)[0])
    z = df["r_next"].to_numpy(float)[tr] / np.sqrt(m.predict(X[tr], cfg.var_floor))
    q = float(np.nanquantile(z[np.isfinite(z)], cfg.var_level))
    vol_ann = sqrt(fv * 252)
    hist = np.sqrt(df["rv_m"].dropna() * 252)
    pctl = float((hist <= vol_ann).mean())
    return {"vol_1d_ann": vol_ann, "daily_move": sqrt(fv), "var95": float(1 - np.exp(q * sqrt(fv))),
            "vol_percentile": pctl, "vol_median": float(hist.median()), "vol_ratio": vol_ann / float(hist.median()),
            "level": level_for(pctl), "hist_start": str(hist.index[0].date()),
            "har_var": fv, "ewma_var": float(df["ewma"].iloc[-1])}  # next-day variance forecasts (ledger)


def market_stats(close: pd.Series, bench: pd.Series | None) -> dict:
    c = close.dropna()
    last = float(c.iloc[-1])
    hi52 = float(c.iloc[-252:].max())
    out = {"last_close": last, "last_date": str(c.index[-1].date()),
           "ret_1m": float(last / c.iloc[-22] - 1) if len(c) > 22 else None,
           "from_52w_high": last / hi52 - 1, "high_52w": hi52, "beta_1y": None, "corr_1y": None}
    if bench is not None and len(bench.dropna()):
        a = c.pct_change().iloc[-252:]
        b = bench.pct_change()
        j = pd.concat([a, b], axis=1, join="inner").dropna()
        if len(j) >= 120:
            cov = np.cov(j.iloc[:, 0], j.iloc[:, 1], ddof=1)
            out["beta_1y"] = float(cov[0, 1] / cov[1, 1])
            out["corr_1y"] = float(np.corrcoef(j.iloc[:, 0], j.iloc[:, 1])[0, 1])
    return out


# --------------------------------------------------------- fundamentals (US)
def us_fundamentals(facts: dict[str, pd.DataFrame], shares: pd.DataFrame, splits: pd.Series,
                    price: pd.Series, asof: pd.Timestamp) -> dict:
    """Point-in-time TTM figures known at `asof` and one year earlier."""
    when = pd.DatetimeIndex([asof - pd.DateOffset(years=1), asof])
    rev = fx.monthly_ttm(fx.quarterly(facts["revenue"]), when, 200)
    ni = fx.monthly_ttm(fx.quarterly(facts["net_income"]), when, 200)
    capex = fx.monthly_ttm(fx.quarterly(facts["capex"]), when, 200).abs()
    sh = fx.monthly_shares(shares, splits, pd.DatetimeIndex([asof]), 200).iloc[0]
    px = float(price.dropna().iloc[-1])
    mcap = px * sh if np.isfinite(sh) else np.nan
    def g(s):
        """YoY growth; None ("not meaningful") for a non-positive base or |growth| > 500%."""
        if not (np.isfinite(s.iloc[0]) and np.isfinite(s.iloc[1])) or s.iloc[0] <= 0:
            return None
        v = float(s.iloc[1] / s.iloc[0] - 1)
        return v if abs(v) <= 5 else None
    last_filed = max((f["filed"].max() for f in facts.values() if not f.empty), default=pd.NaT)
    fin = lambda x: float(x) if np.isfinite(x) else None
    return {
        "ttm_revenue_bn": fin(rev.iloc[1] / 1e9), "ttm_net_income_bn": fin(ni.iloc[1] / 1e9),
        "revenue_growth": g(rev), "net_income_growth": g(ni),
        "pe": fin(mcap / ni.iloc[1]) if np.isfinite(ni.iloc[1]) and ni.iloc[1] > 0 else None,
        "capex_to_revenue": fin(capex.iloc[1] / rev.iloc[1]) if np.isfinite(rev.iloc[1]) and rev.iloc[1] > 0 else None,
        "market_cap_bn": fin(mcap / 1e9) if np.isfinite(mcap) else None,
        "last_filing": None if pd.isna(last_filed) else str(last_filed.date()),
    }


# ------------------------------------------------------------------ driver
def analyze_stock(spec: dict, px: pd.DataFrame, bench: pd.Series | None, cfg: StockConfig,
                  sec: dict | None = None) -> dict:
    close = px["adjclose"].dropna()
    df = daily_frame(close, cfg.lam, cfg.tw_max_abs_logret if spec["market"] == "TW" else None,
                     cfg.rv_d_floor_frac, cfg.stale_run_days)
    fc = walk_forward_var(df, cfg)
    risk = current_risk(df, cfg)
    row = {**{k: spec[k] for k in ("symbol", "market", "segment", "name_en", "name_zh")},
           "history_start": str(close.index[0].date()), **market_stats(close, bench), **risk,
           "backtest": backtest(df, fc, cfg), "fundamentals": None}
    if sec is not None:
        row["fundamentals"] = us_fundamentals(sec["facts"], sec["shares"], sec["splits"], px["close"], close.index[-1])
    tail = df.index[-cfg.chart_days:]
    var_line = -(fc["q_har"] * np.sqrt(fc["f_har"])).shift(1).reindex(tail)  # VaR set the evening before
    row["chart"] = {
        "dates": [str(d.date()) for d in tail],
        "close": [round(float(v), 4) for v in close.reindex(tail)],
        "ret": [round(float(np.expm1(v)), 5) for v in df.loc[tail, "r"]],
        "var95": [None if pd.isna(v) else round(float(1 - np.exp(-v)), 5) for v in var_line],
    }
    return row


def fetch_prices(cache_dir: Path, offline: bool, timeout: float, retries: int, symbols: list[str],
                 already_fetched: set[str] = frozenset()) -> tuple[dict, dict, list]:
    """Download (or read cached) daily bars. Symbols already downloaded by the
    main refresh in this run are read from the cache instead of re-fetched."""
    store = RawStore(Path(cache_dir), offline=offline, timeout=timeout, retries=retries)
    cached = RawStore(Path(cache_dir), offline=True)
    out, warns = {}, []
    for s in symbols:
        try:
            out[s] = yahoo.fetch_daily(cached if s in already_fetched else store, s)
        except FetchError as exc:
            warns.append(f"{s}: {exc}")
    return out, {**cached.manifest, **store.manifest}, warns


def run_stocks(prices: dict[str, pd.DataFrame], raw, watchlist: dict, cfg: StockConfig | None = None,
               markets: tuple[str, ...] = ("US", "TW")) -> dict:
    """Analyse the watchlist names of the given markets. `raw` (main refresh
    data) is only needed for US fundamentals and may be None."""
    cfg = cfg or StockConfig()
    rows, skipped = [], []
    bench_sym = watchlist["benchmarks"]
    for spec in watchlist["stocks"]:
        if spec["market"] not in markets:
            continue
        s = spec["symbol"]
        if s not in prices:
            skipped.append(s)
            continue
        b = prices.get(bench_sym[spec["market"]])
        bench = b["adjclose"] if b is not None else None
        sec = None
        if spec["market"] == "US" and raw is not None and s in raw.sec_facts and s in raw.shares:
            sec = {"facts": raw.sec_facts[s], "shares": raw.shares[s], "splits": raw.splits.get(s, pd.Series(dtype=float))}
        try:
            rows.append(analyze_stock(spec, prices[s], bench, cfg, sec))
        except Exception as exc:  # noqa: BLE001 - one bad series must not drop the page
            log.warning("stock %s skipped: %s", s, exc)
            skipped.append(s)
    return {"stocks": rows, "skipped": skipped, "benchmarks": bench_sym,
            "settings": {"model": "log-HAR on own daily returns (no VIX), fitted on next-5-day mean variance; daily term floored at 5% of the 22-day mean; stale runs (>= 5 unchanged closes) removed; Taiwan |log return| > 25% dropped; EWMA 0.94 baseline",
                         "var": "1-day 95%, filtered historical simulation",
                         "verified_rule": f">= {cfg.min_oos_days} OOS days and Kupiec and Christoffersen p >= {cfg.verify_p}",
                         "light_rule": "next-day vol forecast vs own history of 22-day realized vol: <50th green, 50-80th yellow, >=80th red",
                         "beta": "1-year daily returns vs ^NDX (US) or ^TWII (Taiwan)"}}


def merge_stocks(existing: dict | None, new: dict, markets: tuple[str, ...], watchlist: dict, stamp: str) -> dict:
    """Combine a fresh run for `markets` with the previous file.

    Rows of other markets are kept unchanged. A symbol of a refreshed market
    that failed this time keeps its previous row, marked stale, instead of
    disappearing. Rows are ordered as in the watchlist; per-market update
    stamps are kept in `updated`.
    """
    old_rows = {r["symbol"]: r for r in (existing or {}).get("stocks", [])}
    new_rows = {r["symbol"]: {**r, "stale": False} for r in new["stocks"]}
    rows = []
    for spec in watchlist["stocks"]:
        sym = spec["symbol"]
        if spec["market"] in markets:
            if sym in new_rows:
                rows.append(new_rows[sym])
            elif sym in old_rows:
                rows.append({**old_rows[sym], "stale": True})
        elif sym in old_rows:
            rows.append(old_rows[sym])
    updated = dict((existing or {}).get("updated", {}))
    for m in markets:
        if any(r["market"] == m and not r.get("stale") for r in rows):
            updated[m] = stamp
    out = {**(existing or {}), **new, "stocks": rows, "updated": updated}
    out["skipped"] = new.get("skipped", [])
    return out
