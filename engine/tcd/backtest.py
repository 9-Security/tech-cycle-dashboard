"""Lag-1 portfolio simulation and performance metrics.

Timing convention (no look-ahead):
    target_weight[t]  decided with data up to month-end t
    executed_w[t+1] = target_weight[t]   earns month t+1 returns
    cost[t] = cost_rate * |executed_w[t] - executed_w[t-1]|
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np


@dataclass
class SimResult:
    executed: np.ndarray
    ret: np.ndarray
    cost: np.ndarray
    nav: np.ndarray


def simulate(risk_ret: np.ndarray, safe_ret: np.ndarray, executed: np.ndarray, cost_bps: float) -> SimResult:
    """Simulate given *executed* weights (already lagged)."""
    w = np.asarray(executed, float)
    prev = np.concatenate([[w[0]], w[:-1]])  # no turnover charged on the first month
    cost = cost_bps / 1e4 * np.abs(w - prev)
    ret = w * risk_ret + (1.0 - w) * safe_ret - cost
    nav = np.cumprod(1.0 + ret)
    return SimResult(executed=w, ret=ret, cost=cost, nav=nav)


def lag1(target: np.ndarray, first_weight: float | None = None) -> np.ndarray:
    """executed[t] = target[t-1]; executed[0] = first_weight (default target[0])."""
    t = np.asarray(target, float)
    first = t[0] if first_weight is None else first_weight
    return np.concatenate([[first], t[:-1]])


def max_drawdown(nav: np.ndarray) -> float:
    if len(nav) == 0:
        return float("nan")
    peak = np.maximum.accumulate(np.concatenate([[1.0], nav]))[1:]
    return float(np.min(nav / peak - 1.0))


def metrics(ret: np.ndarray, safe_ret: np.ndarray, executed: np.ndarray | None = None, cost: np.ndarray | None = None) -> dict:
    ret = np.asarray(ret, float)
    n = len(ret)
    if n < 2:
        return {}
    nav = np.cumprod(1.0 + ret)
    years = n / 12.0
    ex = ret - safe_ret
    sd = ex.std(ddof=1)
    downside = ex[ex < 0]
    dd_sd = sqrt(np.mean(np.square(downside))) if len(downside) else np.nan
    cagr = nav[-1] ** (1.0 / years) - 1.0
    mdd = max_drawdown(nav)
    out = {
        "months": n,
        "sharpe": float(ex.mean() / sd * sqrt(12)) if sd > 0 else float("nan"),
        "sortino": float(ex.mean() / dd_sd * sqrt(12)) if dd_sd and dd_sd > 0 else float("nan"),
        "cagr": float(cagr),
        "ann_vol": float(ret.std(ddof=1) * sqrt(12)),
        "max_dd": mdd,
        "calmar": float(cagr / abs(mdd)) if mdd < 0 else float("nan"),
        "period_return": float(nav[-1] - 1.0),
        "final_nav": float(nav[-1]),
        "skew": float(_skew(ex)),
        "kurtosis": float(_kurt(ex)),
        "sharpe_monthly": float(ex.mean() / sd) if sd > 0 else float("nan"),
    }
    if executed is not None:
        w = np.asarray(executed, float)
        out["ann_turnover"] = float(np.abs(np.diff(w)).sum() / years)
        out["avg_weight"] = float(w.mean())
    if cost is not None:
        out["total_cost"] = float(np.sum(cost))
    return out


def _skew(x: np.ndarray) -> float:
    x = x - x.mean()
    s = x.std()
    return float(np.mean(x**3) / s**3) if s > 0 else 0.0


def _kurt(x: np.ndarray) -> float:
    """Non-excess kurtosis (normal = 3)."""
    x = x - x.mean()
    s = x.std()
    return float(np.mean(x**4) / s**4) if s > 0 else 3.0


def objective(ret: np.ndarray, safe_ret: np.ndarray, mdd_budget: float, mdd_penalty: float) -> float:
    ex = ret - safe_ret
    sd = ex.std(ddof=1)
    if not sd > 0:
        return -np.inf
    sharpe = ex.mean() / sd * sqrt(12)
    mdd = max_drawdown(np.cumprod(1.0 + ret))
    return float(sharpe - mdd_penalty * max(0.0, -mdd - mdd_budget))
