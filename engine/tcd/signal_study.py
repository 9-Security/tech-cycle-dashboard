"""Stand-alone predictive tests of individual signals, independent of the
regime rules.

Everything here is descriptive research. Forward windows overlap, so plain
t-stats are invalid: we use Newey-West (HAC) t-stats and a moving-block
bootstrap. Bucket edges are point-in-time (expanding history only).
"""

from __future__ import annotations

from math import sqrt

import numpy as np
import pandas as pd

HORIZONS = (1, 3, 6, 12)

SIGNALS = {
    "overheat_score": "Overheat score ((val_z + capex_z) / 2)",
    "val_z": "Valuation z (P/E from 2013, price extension before)",
    "capex_z": "Capex intensity z",
    "earn_score": "Earnings momentum score",
    "vix": "VIX (monthly mean)",
}
# Side of the signal on which the regime engine de-risks.
DERISK_SIDE = {"overheat_score": "high", "val_z": "high", "capex_z": "high", "earn_score": "low", "vix": "high"}

ERAS = {
    "1993-2012 (macro proxies)": ("1993-01-31", "2012-12-31"),
    "2013+ (SEC firm-level)": ("2013-01-31", "2100-12-31"),
}


# --------------------------------------------------------------- targets
def forward_excess(risk: pd.Series, safe: pd.Series, h: int) -> pd.Series:
    """Cumulative log excess return over months t+1..t+h, aligned at t."""
    lx = np.log1p(risk) - np.log1p(safe)
    out = sum(lx.shift(-k) for k in range(1, h + 1))
    return out


def forward_max_drawdown(risk: pd.Series, h: int = 12) -> pd.Series:
    """Worst peak-to-trough of the risk asset over t+1..t+h (start at 1.0 at t)."""
    r = risk.to_numpy(float)
    n = len(r)
    out = np.full(n, np.nan)
    for t in range(n - h):
        path = np.cumprod(1.0 + r[t + 1 : t + 1 + h])
        if np.isnan(path).any():
            continue
        peak = np.maximum.accumulate(np.concatenate([[1.0], path]))[1:]
        out[t] = float(np.min(path / peak - 1.0))
    return pd.Series(out, index=risk.index)


# ------------------------------------------------------------- statistics
def pit_buckets(s: pd.Series, n: int = 5, min_hist: int = 60) -> pd.Series:
    """Bucket 1..n of s_t by its percentile within s_1..s_t (expanding)."""
    v = s.to_numpy(float)
    out = np.full(len(v), np.nan)
    hist: list[float] = []
    for i, x in enumerate(v):
        if np.isnan(x):
            continue
        hist.append(x)
        if len(hist) < min_hist:
            continue
        arr = np.asarray(hist)
        pct = (np.sum(arr < x) + 0.5 * np.sum(arr == x)) / len(arr)
        out[i] = min(n, int(pct * n) + 1)
    return pd.Series(out, index=s.index)


def _rank(a: np.ndarray) -> np.ndarray:
    return pd.Series(a).rank().to_numpy()


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    if len(x) < 3:
        return float("nan")
    return float(np.corrcoef(_rank(x), _rank(y))[0, 1])


def newey_west(y: np.ndarray, x: np.ndarray, lag: int) -> tuple[float, float]:
    """OLS slope of y on standardized x with Newey-West (Bartlett) t-stat."""
    n = len(y)
    if n < 10:
        return float("nan"), float("nan")
    xs = (x - x.mean()) / x.std(ddof=1)
    X = np.column_stack([np.ones(n), xs])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    u = y - X @ beta
    Xu = X * u[:, None]
    S = Xu.T @ Xu
    for L in range(1, lag + 1):
        w = 1.0 - L / (lag + 1.0)
        G = Xu[L:].T @ Xu[:-L]
        S += w * (G + G.T)
    XtX_inv = np.linalg.inv(X.T @ X)
    V = XtX_inv @ S @ XtX_inv
    se = sqrt(V[1, 1]) if V[1, 1] > 0 else float("nan")
    return float(beta[1]), float(beta[1] / se) if se and se > 0 else float("nan")


def hodrick_t(y: np.ndarray, x: np.ndarray, r1: np.ndarray, h: int) -> tuple[float, float]:
    """OLS slope of the h-month overlapping return y on standardized x, with a
    Hodrick (1992) "1B" t-stat.

    Newey-West with lag h-1 over-rejects badly when x is persistent (AR ~0.95)
    and the target overlaps (simulated size 13-21% at a nominal 5%). Hodrick's
    estimator rewrites the overlapping regression as one-month returns r1 on the
    rolling sum of the last h regressors and uses heteroskedasticity-robust
    variance under the null of no predictability; its size stays close to
    nominal with persistent regressors (Ang & Bekaert 2007).

    y, x, r1 are aligned at t: y[t] = sum of excess log returns t+1..t+h,
    r1[t] = excess log return t+1. Rows must be consecutive months."""
    n = len(y)
    if n < max(10, 2 * h):
        return float("nan"), float("nan")
    sd = x.std(ddof=1)
    if not sd > 0:
        return float("nan"), float("nan")
    xs = (x - x.mean()) / sd
    X = np.column_stack([np.ones(n), xs])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    eps = r1 - r1.mean()  # one-month residual under H0 (no predictability)
    Z = np.cumsum(X, axis=0)
    Z[h:] = Z[h:] - Z[:-h]  # z_t = sum_{j=0}^{h-1} X_{t-j}
    ok = np.arange(n) >= h - 1
    Zt, et = Z[ok], eps[ok]
    S = (Zt * (et ** 2)[:, None]).T @ Zt
    XtX_inv = np.linalg.inv(X.T @ X)
    V = XtX_inv @ S @ XtX_inv
    se = sqrt(V[1, 1]) if V[1, 1] > 0 else float("nan")
    return float(beta[1]), float(beta[1] / se) if se and se > 0 else float("nan")


def block_bootstrap_spread(bucket: np.ndarray, y: np.ndarray, n_buckets: int, block: int = 12,
                           reps: int = 1000, seed: int = 0) -> tuple[float, float, float]:
    """Top-minus-bottom bucket mean of y with a moving-block bootstrap 90% CI."""
    def spread(b, v):
        hi, lo = v[b == n_buckets], v[b == 1]
        return hi.mean() - lo.mean() if len(hi) and len(lo) else np.nan

    point = spread(bucket, y)
    n = len(y)
    if n < 2 * block:
        return float(point), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    starts_max = n - block
    k = int(np.ceil(n / block))
    stats = np.empty(reps)
    for r in range(reps):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.integers(0, starts_max + 1, k)])[:n]
        stats[r] = spread(bucket[idx], y[idx])
    lo, hi = np.nanpercentile(stats, [5, 95])
    return float(point), float(lo), float(hi)


def shift_test_spread(bucket: np.ndarray, y: np.ndarray, n_buckets: int, min_shift: int = 24) -> tuple[float, float, float, float]:
    """Top-minus-bottom bucket mean of y and its null distribution from circular
    shifts of the bucket series against y (each series keeps its own
    autocorrelation; only their alignment is broken).

    Returns (spread, null 5th pct, null 95th pct, two-sided p). A moving-block
    bootstrap CI under-covers here whatever the block length (simulated miss
    rate ~20% for a nominal 10% with AR 0.96-0.985 signals and 12-month
    overlapping targets), so verdicts use this test instead."""
    def spread(b, v):
        hi, lo = v[b == n_buckets], v[b == 1]
        return hi.mean() - lo.mean() if len(hi) and len(lo) else np.nan

    n = len(y)
    point = spread(bucket, y)
    if n < 4 * min_shift or not np.isfinite(point):
        return float(point), float("nan"), float("nan"), float("nan")
    null = np.array([spread(np.roll(bucket, k), y) for k in range(min_shift, n - min_shift + 1)])
    null = null[np.isfinite(null)]
    lo, hi = np.percentile(null, [5, 95])
    p = float((np.abs(null) >= abs(point)).mean())
    return float(point), float(lo), float(hi), p


def verdict_p(point: float, p: float, kind: str, side: str = "high", alpha: float = 0.05) -> str:
    """Plain reading of a top-minus-bottom spread from its circular-shift p-value.
    alpha 0.05: simulated false-positive rate 5-10% for these persistent signals."""
    if not (np.isfinite(point) and np.isfinite(p)):
        return "insufficient data"
    if p >= alpha:
        return f"inconclusive (shift-test p = {p:.2f})"
    lo = hi = -point if side == "low" else point
    return verdict(lo, hi, kind, "high") .replace("high signal", f"{side} signal")


def verdict(lo: float, hi: float, kind: str, side: str = "high") -> str:
    """Plain reading of a top-minus-bottom bucket CI from the de-risking side.

    `side` is where the engine de-risks ("high" or "low" signal values)."""
    if not (np.isfinite(lo) and np.isfinite(hi)):
        return "insufficient data"
    if side == "low":  # de-risk side is the bottom bucket: flip the spread
        lo, hi = -hi, -lo
    who = f"{side} signal"
    if kind == "return":
        if hi < 0:
            return f"supports de-risking: {who} preceded LOWER returns"
        if lo > 0:
            return f"contradicts de-risking: {who} preceded HIGHER returns"
        return "inconclusive (CI spans 0)"
    if lo > 0:
        return f"supports de-risking: {who} preceded MORE large drawdowns"
    if hi < 0:
        return f"contradicts de-risking: {who} preceded FEWER large drawdowns"
    return "inconclusive (CI spans 0)"


# ----------------------------------------------------------------- study
def _valid(*arrs) -> np.ndarray:
    m = np.ones(len(arrs[0]), bool)
    for a in arrs:
        m &= ~np.isnan(a)
    return m


def run_study(panel: pd.DataFrame, start: str = "1993-01-31", n_buckets: int = 5, min_hist: int = 60,
              thresholds: tuple[float, ...] = (1.0, 1.5, 2.0), dd_cut: float = -0.20) -> dict:
    complete = panel[~panel["partial"].astype(bool)]
    risk, safe = complete["risk_ret"], complete["safe_ret"]
    fwd = {h: forward_excess(risk, safe, h) for h in HORIZONS}
    fdd = forward_max_drawdown(risk, 12)
    window = complete.index >= pd.Timestamp(start)

    ic_rows, bucket_rows, era_rows = [], [], []
    for sig, label in SIGNALS.items():
        s_full = complete[sig]
        # Buckets use all history available at t (incl. pre-`start` warm-up).
        b_full = pit_buckets(s_full, n_buckets, min_hist)
        s = s_full[window].to_numpy(float)
        b = b_full[window].to_numpy(float)
        for h in HORIZONS:
            y = fwd[h][window].to_numpy(float)
            r1 = fwd[1][window].to_numpy(float)
            m = _valid(s, y, r1)
            beta, t = hodrick_t(y[m], s[m], r1[m], h)
            _, t_nw = newey_west(y[m], s[m], max(h - 1, 0))
            ic_rows.append({"signal": sig, "label": label, "horizon": h, "n": int(m.sum()),
                            "ic": spearman(s[m], y[m]), "beta_per_sd": beta, "t": t, "nw_t_naive": t_nw})

        y12 = fwd[12][window].to_numpy(float)
        dd = fdd[window].to_numpy(float)
        m = _valid(b, y12, dd)
        point, lo, hi, pv = shift_test_spread(b[m].astype(int), y12[m], n_buckets)
        dpoint, dlo, dhi, dpv = shift_test_spread(b[m].astype(int), (dd[m] < dd_cut).astype(float), n_buckets)
        buckets = []
        for q in range(1, n_buckets + 1):
            mq = m & (b == q)
            buckets.append({
                "bucket": q, "n": int(mq.sum()),
                "fwd12_mean": float(np.mean(y12[mq])) if mq.any() else None,
                "fwd12_hit": float(np.mean(y12[mq] > 0)) if mq.any() else None,
                "fwd_dd12_mean": float(np.mean(dd[mq])) if mq.any() else None,
                "p_dd_below": float(np.mean(dd[mq] < dd_cut)) if mq.any() else None,
            })
        bucket_rows.append({"signal": sig, "label": label, "buckets": buckets,
                            "spread_top_minus_bottom": point, "spread_null90": [lo, hi], "spread_p": pv,
                            "dd_prob_spread": dpoint, "dd_prob_spread_null90": [dlo, dhi], "dd_prob_spread_p": dpv,
                            "derisk_side": DERISK_SIDE[sig],
                            "return_verdict": verdict_p(point, pv, "return", DERISK_SIDE[sig]),
                            "risk_verdict": verdict_p(dpoint, dpv, "risk", DERISK_SIDE[sig])})

        for era, (a, z) in ERAS.items():
            # Forward 12-month windows must end inside the era (the 1993-2012
            # era used to include windows running into 2013 returns).
            em = (complete.index >= pd.Timestamp(a)) & (complete.index <= pd.Timestamp(z) - pd.offsets.MonthEnd(12))
            se_ = s_full[em].to_numpy(float)
            ye = fwd[12][em].to_numpy(float)
            r1e = fwd[1][em].to_numpy(float)
            mm = _valid(se_, ye, r1e)
            beta, t = hodrick_t(ye[mm], se_[mm], r1e[mm], 12)
            era_rows.append({"signal": sig, "era": era, "n": int(mm.sum()),
                             "ic_12m": spearman(se_[mm], ye[mm]), "t_12m": t})

    # Threshold events on the overheat score (the strategy's actual trigger).
    s = complete["overheat_score"][window].to_numpy(float)
    y12 = fwd[12][window].to_numpy(float)
    dd = fdd[window].to_numpy(float)
    m = _valid(s, y12, dd)
    thr_rows = []
    for thr in thresholds:
        above, below = m & (s > thr), m & (s <= thr)
        thr_rows.append({
            "threshold": thr,
            "months_above": int(above.sum()),
            "share_above": float(above.sum() / m.sum()),
            "fwd12_above": float(np.mean(y12[above])) if above.any() else None,
            "fwd12_below": float(np.mean(y12[below])) if below.any() else None,
            "p_dd_above": float(np.mean(dd[above] < dd_cut)) if above.any() else None,
            "p_dd_below": float(np.mean(dd[below] < dd_cut)) if below.any() else None,
        })

    unconditional = {
        "fwd12_mean": float(np.nanmean(fwd[12][window])),
        "p_dd_below": float(np.nanmean(fdd[window].dropna() < dd_cut)),
    }
    plot = complete.loc[window, ["overheat_score"]].copy()
    plot["fwd12"] = fwd[12][window]
    plot = plot.dropna()
    return {
        "window": {"start": str(complete.index[window][0].date()), "end": str(complete.index[window][-1].date()),
                   "last_month_with_12m_forward": str(plot.index[-1].date()) if len(plot) else None},
        "settings": {"horizons": list(HORIZONS), "n_buckets": n_buckets, "bucket_min_history": min_hist,
                     "drawdown_cut": dd_cut, "target": "cumulative log excess return of risk asset over T-bills",
                     "spread_test": "circular-shift test of bucket series vs forward outcome (shifts >= 24 months), two-sided; verdict at p < 0.05",
                     "t_stat": "Hodrick (1992) 1B on overlapping targets"},
        "unconditional": unconditional,
        "ic": ic_rows,
        "buckets": bucket_rows,
        "eras": era_rows,
        "thresholds": thr_rows,
        "scatter": {"dates": [str(d.date()) for d in plot.index],
                    "overheat_score": [round(float(x), 4) for x in plot["overheat_score"]],
                    "fwd12": [round(float(x), 5) for x in plot["fwd12"]]},
    }
