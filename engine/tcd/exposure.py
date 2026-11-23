"""Volatility-based suggested maximum exposure (methodology section 21).

Registered 2026-11-23, before its history was computed. Display only: it does
not change v2 (live posture) or v3 (candidate).

    sigma_hat = live 5-day volatility forecast, annualized (HAR + VIX)
    target    = median 22-day realized vol of all days up to the latest close
    cap       = min(1, target / sigma_hat), rounded DOWN to a 5-point step
    band      = A 100% | B 75-95% | C 50-70% | D 25-45% | E below 25%
"""
from __future__ import annotations

import bisect
from math import floor, sqrt

import numpy as np
import pandas as pd

STEP = 0.05
BANDS = ((1.0, "A"), (0.75, "B"), (0.50, "C"), (0.25, "D"), (0.0, "E"))  # lower bounds
WHIPSAW_DAYS = 5
REVIEW_CHANGES_PER_YEAR = 24
REVIEW_WHIPSAW_SHARE = 0.30
DD_WINDOWS = (("dotcom", "2000-03-01", "2002-10-31"), ("gfc", "2007-10-01", "2009-03-31"),
              ("covid", "2020-02-01", "2020-03-31"), ("2022", "2022-01-01", "2022-10-31"))
RULE = {"sigma_hat": "live 5-day volatility forecast (HAR + VIX), annualized",
        "target": "median 22-day realized volatility since 1990, point-in-time",
        "cap": "min(1, target / sigma_hat), rounded down to 5 points", "bands": "A 100% | B 75-95% | C 50-70% | D 25-45% | E <25%"}


def cap_for(target_vol: float, forecast_vol: float) -> tuple[float, float]:
    """(unrounded, published) cap."""
    if not (np.isfinite(target_vol) and np.isfinite(forecast_vol)) or forecast_vol <= 0:
        raise ValueError("cap needs finite positive volatilities")
    raw = min(1.0, target_vol / forecast_vol)
    return raw, round(floor(raw / STEP + 1e-9) * STEP, 2)


def band_for(cap: float) -> str:
    for lo, name in BANDS:
        if cap >= lo - 1e-9:
            return name
    return "E"


def current(short_current: dict) -> dict:
    sigma, target = float(short_current["vol_5d_ann"]), float(short_current["vol_hist_median"])
    raw, cap = cap_for(target, sigma)
    return {"date": short_current["date"], "forecast_vol_5d_ann": sigma, "target_vol": target,
            "cap_raw": raw, "cap": cap, "band": band_for(cap), "rule": RULE}


def stability(levels: pd.Series) -> dict:
    """Changes per year, median run length, share of changes reversed within WHIPSAW_DAYS."""
    v = levels.dropna().to_numpy()
    if len(v) < 2:
        return {"n_days": int(len(v))}
    ch = np.flatnonzero(v[1:] != v[:-1]) + 1  # index of the first day of each new level
    years = len(v) / 252
    rev = 0
    for k, i in enumerate(ch):
        nxt = ch[k + 1] if k + 1 < len(ch) else None
        if nxt is not None and nxt - i <= WHIPSAW_DAYS and v[nxt] == v[i - 1]:
            rev += 1
    runs = np.diff(np.concatenate([[0], ch, [len(v)]]))
    out = {"n_days": int(len(v)), "changes": int(len(ch)), "changes_per_year": float(len(ch) / years),
           "median_run_days": float(np.median(runs)), "whipsaw_share": float(rev / len(ch)) if len(ch) else 0.0,
           "share_by_level": {str(k): float(c / len(v)) for k, c in zip(*np.unique(v, return_counts=True))}}
    out["review_triggered"] = bool(out["changes_per_year"] >= REVIEW_CHANGES_PER_YEAR
                                   or out["whipsaw_share"] >= REVIEW_WHIPSAW_SHARE)
    return out


def _max_dd(simple: pd.Series) -> float:
    nav = (1 + simple).cumprod()
    return float((nav / nav.cummax() - 1).min()) if len(nav) else float("nan")


def history(df: pd.DataFrame, fc: pd.DataFrame, live_model: str, oos_start_year: int) -> dict:
    """Backtest context from walk-forward forecasts (nothing is tuned on it)."""
    from .light import level_for
    hist = np.sqrt(df["rv_m"] * 252)
    target = hist.expanding().median()
    s5 = np.sqrt(fc[f"{live_model}_5"] * 252)
    s1 = np.sqrt(fc[f"{live_model}_1"] * 252)
    oos = (df.index.year >= oos_start_year) & s5.notna() & s1.notna() & target.notna()
    raw = (target / s5).clip(upper=1.0)
    cap = (np.floor(raw / STEP + 1e-9) * STEP).round(2).where(oos)
    band = cap.map(lambda c: band_for(c) if pd.notna(c) else None)
    # Light history: 1-day forecast ranked against 22-day realized vol known by that close.
    seen, lev = [], []
    for t, h, f in zip(df.index, hist.to_numpy(), s1.to_numpy()):
        if np.isfinite(h):
            bisect.insort(seen, h)
        lev.append(level_for(bisect.bisect_right(seen, f) / len(seen)) if (np.isfinite(f) and seen) else None)
    light = pd.Series(lev, index=df.index).where(oos)
    r = np.expm1(df["r_next"]).where(oos & df["r_next"].notna()).dropna()
    capped = (cap.reindex(r.index) * r)
    out = {"from": str(r.index[0].date()) if len(r) else None, "n_days": int(len(r)),
           "avg_cap": float(cap.dropna().mean()), "share_below_full": float((cap.dropna() < 1).mean()),
           "vol_ann": {"capped": float(capped.std() * sqrt(252)), "buy_hold": float(r.std() * sqrt(252))},
           "max_dd": {"capped": _max_dd(capped), "buy_hold": _max_dd(r)}, "windows": {},
           "cap_stability": stability(band), "light_stability": stability(light)}
    for name, a, b in DD_WINDOWS:
        m = (r.index >= a) & (r.index <= b)
        if m.any():
            out["windows"][name] = {"from": a, "to": b, "avg_cap": float(cap.reindex(r.index)[m].mean()),
                                    "max_dd_capped": _max_dd(capped[m]), "max_dd_buy_hold": _max_dd(r[m])}
    return out
