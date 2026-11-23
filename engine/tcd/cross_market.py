"""Out-of-domain test: apply the frozen v3 design to markets it never saw.

Pre-registered on 2026-11-23, BEFORE running on real data (see git history
of this file). Nothing in the v3 specification (TiltGrid, walk-forward
procedure, objective, costs) is changed per market.

Signals per market:
  * price-extension z, 21d/63d realized vol and the VIX-implied vol are
    computed from each market's OWN prices (the transferable core of v3);
  * tech fundamentals (aggregate P/E, Capex intensity, earnings momentum)
    are used only for the tech-themed market (^SOX); elsewhere they are
    missing and the model treats them as neutral (coefficient has no
    effect, earnings cut never fires). The grid is identical everywhere.

Success criteria (fixed in advance; reported pass/fail as-is):
  C1  v3 OOS Sharpe > vol-matched buy & hold Sharpe in >= 6 of 9 markets
  C2  mean Sharpe difference across markets > 0 with a 90% joint
      moving-block bootstrap CI (12-month calendar blocks shared by all
      markets, preserving cross-market correlation) excluding 0
  C3  (secondary) v3 Max DD better than vol-matched buy & hold in >= 6 of 9
Overall pass = C1 and C2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import metrics, simulate
from .config import BacktestConfig, FeatureConfig, TiltGrid
from .features import rolling_z
from .sources import yahoo
from .sources.http import FetchError
from .sources.store import RawStore
from .validation import BTData, nested_walk_forward, prepare, run_grid

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Market:
    symbol: str
    name: str
    tech_theme: bool  # gets the tech fundamental signals


MARKETS: tuple[Market, ...] = (
    Market("^SOX", "Semiconductors (PHLX SOX, price index)", True),
    Market("SPY", "US large caps (S&P 500)", False),
    Market("XLF", "US financials", False),
    Market("XLE", "US energy", False),
    Market("XLV", "US health care", False),
    Market("EWJ", "Japan (USD)", False),
    Market("EWG", "Germany (USD)", False),
    Market("EWU", "United Kingdom (USD)", False),
    Market("EEM", "Emerging markets (USD)", False),
)

CRITERIA = {
    "registered": "2026-11-23",
    "C1_min_markets_sharpe": 6,
    "C2_ci_level": 0.90,
    "C3_min_markets_mdd": 6,
    "bootstrap_block_months": 12,
    "bootstrap_reps": 5000,
}


def _monthly_last(s: pd.Series, months: pd.DatetimeIndex) -> pd.Series:
    return s.resample("ME").last().reindex(months)


def market_panel(px: pd.DataFrame, vix: pd.Series, tbill: pd.Series, tech_panel: pd.DataFrame | None,
                 fcfg: FeatureConfig, last_complete: pd.Timestamp) -> pd.DataFrame:
    """Monthly PIT panel for one market, complete months only."""
    close = px["adjclose"].dropna()
    start = close.index.min() + pd.offsets.MonthEnd(0)
    months = pd.date_range(start, last_complete, freq="ME")
    p = pd.DataFrame(index=months)
    m_close = _monthly_last(close, months)
    p["risk_ret"] = m_close.pct_change(fill_method=None)
    tb = _monthly_last(tbill.ffill(), months).ffill()
    p["safe_ret"] = tb.shift(1) / 100.0 / 12.0
    ext = close / close.rolling(fcfg.val_ma_days, min_periods=fcfg.val_ma_days).mean() - 1.0
    p["val_z_proxy"] = rolling_z(_monthly_last(ext, months), fcfg.val_z_window, fcfg.val_z_min)
    dret = np.log(close).diff()
    for w in (21, 63):
        p[f"rv{w}"] = _monthly_last(dret.rolling(w, min_periods=int(w * 0.8)).std() * np.sqrt(252), months)
    vix_m = vix.resample("ME")
    p["vix"] = vix_m.mean().reindex(months)
    vix_last = vix_m.last().reindex(months)
    ratio = (p["rv63"] / (vix_last / 100.0)).rolling(fcfg.vix_ratio_months, min_periods=12).median()
    p["vol_vix"] = vix_last / 100.0 * ratio
    for col in ("val_z_pe", "capex_z", "earn_score"):
        p[col] = tech_panel[col].reindex(months) if (tech_panel is not None and col in tech_panel) else np.nan
    # Regime-model columns are not used by v3; keep prepare() happy.
    p["overheat_score"] = np.nan
    p["partial"] = False
    return p


def _windows(panel: pd.DataFrame, bcfg: BacktestConfig) -> tuple[str, int]:
    need = ["risk_ret", "safe_ret", "val_z_proxy", "rv21", "rv63", "vol_vix"]
    first = panel.dropna(subset=need).index.min()
    train_start = first + pd.offsets.MonthEnd(1)  # prepare() needs one prior month of signals
    months_to = lambda y: len(pd.date_range(train_start, pd.Timestamp(f"{y - 1}-12-31"), freq="ME"))
    year = train_start.year + 1
    while months_to(year) < bcfg.min_train_months:
        year += 1
    return str(train_start.date()), year


@dataclass
class MarketResult:
    market: Market
    dates: pd.DatetimeIndex
    v3_ret: np.ndarray
    bh_ret: np.ndarray
    safe: np.ndarray
    row: dict


def evaluate_market(market: Market, panel: pd.DataFrame, grid: TiltGrid, bcfg: BacktestConfig) -> MarketResult:
    train_start, oos_year = _windows(panel, bcfg)
    mcfg = replace(bcfg, train_start=train_start, oos_start_year=oos_year)
    bt: BTData = prepare(panel, mcfg)
    live_year = int(bt.dates[-1].year)
    wf = nested_walk_forward(bt, run_grid(bt, list(grid), mcfg.cost_bps), mcfg, live_year)
    mask = bt.dates >= wf.dates[0]
    safe, risk = bt.safe[mask], bt.risk[mask]
    bh = simulate(risk, safe, np.ones(len(risk)), mcfg.cost_bps)
    m3 = metrics(wf.sim.ret, safe, wf.sim.executed, wf.sim.cost)
    mb = metrics(bh.ret, safe)
    c = min(1.0, m3["ann_vol"] / mb["ann_vol"]) if mb["ann_vol"] > 0 else 1.0
    vm = metrics(c * risk + (1 - c) * safe, safe)
    last = wf.folds[-1]["params"]
    row = {
        "symbol": market.symbol, "name": market.name, "tech_theme": market.tech_theme,
        "oos_start": str(wf.dates[0].date()), "oos_end": str(wf.dates[-1].date()), "months": int(len(wf.dates)),
        "v3_sharpe": m3["sharpe"], "bh_sharpe": mb["sharpe"], "vm_sharpe": vm["sharpe"],
        "sharpe_diff": m3["sharpe"] - vm["sharpe"],
        "v3_max_dd": m3["max_dd"], "vm_max_dd": vm["max_dd"], "bh_max_dd": mb["max_dd"],
        "v3_cagr": m3["cagr"], "bh_cagr": mb["cagr"], "vm_cagr": vm["cagr"],
        "v3_vol": m3["ann_vol"], "bh_vol": mb["ann_vol"], "avg_weight": m3.get("avg_weight"), "risk_fraction": c,
        "beats_sharpe": bool(m3["sharpe"] > vm["sharpe"]), "beats_mdd": bool(m3["max_dd"] > vm["max_dd"]),
        "last_params": {k: last[k] for k in ("c_px", "c_pe", "c_capex", "base", "earn_cut", "vol_input", "vol_target")},
    }
    return MarketResult(market, wf.dates, wf.sim.ret, bh.ret, safe, row)


def _sharpe(r: np.ndarray, s: np.ndarray) -> float:
    ex = r - s
    sd = ex.std(ddof=1)
    return float(ex.mean() / sd * np.sqrt(12)) if sd > 0 else float("nan")


def pooled_bootstrap(results: list[MarketResult], block: int, reps: int, level: float, seed: int = 0) -> dict:
    """Mean (v3 - buy&hold) Sharpe difference across markets with a joint
    calendar-block bootstrap. Vol-matched B&H has the same excess Sharpe as
    B&H, so B&H returns are used directly."""
    union = sorted(set().union(*[set(r.dates) for r in results]))
    U = pd.DatetimeIndex(union)
    pos = [U.get_indexer(r.dates) for r in results]
    n = len(U)
    k = int(np.ceil(n / block))
    rng = np.random.default_rng(seed)
    point = float(np.mean([_sharpe(r.v3_ret, r.safe) - _sharpe(r.bh_ret, r.safe) for r in results]))
    stats = np.empty(reps)
    for i in range(reps):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.integers(0, n - block + 1, k)])[:n]
        diffs = []
        for r, p in zip(results, pos):
            # map sampled calendar months to this market's rows (skip months it did not trade)
            inv = np.full(n, -1)
            inv[p] = np.arange(len(p))
            rows = inv[idx]
            rows = rows[rows >= 0]
            if len(rows) < 24:
                continue
            diffs.append(_sharpe(r.v3_ret[rows], r.safe[rows]) - _sharpe(r.bh_ret[rows], r.safe[rows]))
        stats[i] = np.mean(diffs) if diffs else np.nan
    a = (1 - level) / 2
    lo, hi = np.nanpercentile(stats, [100 * a, 100 * (1 - a)])
    return {"mean_sharpe_diff": point, "ci": [float(lo), float(hi)], "p_positive": float(np.nanmean(stats > 0)),
            "union_months": n, "level": level}


def verdict(rows: list[dict], pooled: dict) -> dict:
    n = len(rows)
    n_sh = sum(r["beats_sharpe"] for r in rows)
    n_dd = sum(r["beats_mdd"] for r in rows)
    c1 = n_sh >= CRITERIA["C1_min_markets_sharpe"]
    c2 = pooled["mean_sharpe_diff"] > 0 and pooled["ci"][0] > 0
    c3 = n_dd >= CRITERIA["C3_min_markets_mdd"]
    return {
        "C1": {"pass": c1, "detail": f"{n_sh}/{n} markets with higher Sharpe (need {CRITERIA['C1_min_markets_sharpe']})"},
        "C2": {"pass": c2, "detail": f"mean diff {pooled['mean_sharpe_diff']:+.3f}, {int(pooled['level'] * 100)}% CI "
                                      f"[{pooled['ci'][0]:+.3f}, {pooled['ci'][1]:+.3f}]"},
        "C3": {"pass": c3, "detail": f"{n_dd}/{n} markets with smaller Max DD (need {CRITERIA['C3_min_markets_mdd']})"},
        "overall_pass": bool(c1 and c2),
        "n_sharpe": n_sh, "n_mdd": n_dd, "n_markets": n,
    }


def fetch_markets(cache_dir: Path, offline: bool, timeout: float, retries: int) -> tuple[dict[str, pd.DataFrame], dict, list[str]]:
    store = RawStore(Path(cache_dir), offline=offline, timeout=timeout, retries=retries)
    data, warnings = {}, []
    for m in MARKETS:
        try:
            data[m.symbol] = yahoo.fetch_daily(store, m.symbol)
        except FetchError as exc:
            warnings.append(f"{m.symbol}: {exc}")
    return data, dict(store.manifest), warnings


def run_cross_market(prices: dict[str, pd.DataFrame], vix: pd.Series, tbill: pd.Series, tech_panel: pd.DataFrame,
                     fcfg: FeatureConfig, bcfg: BacktestConfig, grid: TiltGrid) -> dict:
    complete = tech_panel[~tech_panel["partial"].astype(bool)]
    last_complete = complete.index[-1]
    results, skipped = [], []
    for m in MARKETS:
        if m.symbol not in prices:
            skipped.append(m.symbol)
            continue
        panel = market_panel(prices[m.symbol], vix, tbill, complete if m.tech_theme else None, fcfg, last_complete)
        results.append(evaluate_market(m, panel, grid, bcfg))
        log.info("cross-market %s: v3 %.2f vs B&H %.2f", m.symbol, results[-1].row["v3_sharpe"], results[-1].row["bh_sharpe"])
    rows = [r.row for r in results]
    pooled = pooled_bootstrap(results, CRITERIA["bootstrap_block_months"], CRITERIA["bootstrap_reps"], CRITERIA["C2_ci_level"])
    return {"criteria": CRITERIA, "markets": rows, "pooled": pooled, "verdict": verdict(rows, pooled),
            "skipped": skipped, "spec": "v3 TiltGrid and walk-forward unchanged; per-market price/vol signals; "
                                         "tech fundamentals only for ^SOX"}
