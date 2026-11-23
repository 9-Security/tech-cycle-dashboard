"""Pre-registered challenger for the market 1-day 95% VaR (methodology section 18).

Registered 2026-11-23, before any live outcome of either model existed.

Problem. The live VaR (HAR+VIX variance, filtered historical simulation) takes
its 5% quantile from an EXPANDING window of earlier out-of-sample standardized
returns, updated once a year. Over 2000-2026 it covers (4.76% breaches), but
over the last three years it breached 7.15% of days (Kupiec p 0.011): the
quantile adapts slowly.

Challenger (the only one). Same variance forecast; the quantile is the 5%
quantile of the most recent WINDOW = 500 out-of-sample standardized returns
(about two years), updated DAILY. The window was fixed on that principle
before any result of this challenger was computed and will not be tuned.

Decision rule (fixed now). Both are logged side by side in the market ledger
(targets var_1d and var_1d_challenger) and compared only on live days scored
for both. After >= 250 such days: recommend switching ONLY if the incumbent
fails (Kupiec or Christoffersen p < 0.05) and the challenger passes both;
otherwise keep the incumbent. The owner decides; nothing switches
automatically. The backtest below is published as context, not as evidence:
the same window was used to find the problem.
"""

from __future__ import annotations

from math import exp, sqrt

import numpy as np
import pandas as pd

from .short_risk import christoffersen, kupiec

WINDOW = 500
LEVEL = 0.05
MIN_LIVE_DAYS = 250


def rolling_quantile(df: pd.DataFrame, fc: pd.DataFrame, model: str, window: int = WINDOW,
                     level: float = LEVEL) -> pd.Series:
    """Quantile usable for the forecast made at the close of day t: the
    standardized returns z_s = r_{s->s+1} / sqrt(f_s) of out-of-sample
    forecasts with s <= t-1 (their outcome is known at the close of t)."""
    f = fc[f"{model}_1"]
    z = (df["r_next"] / np.sqrt(f)).where(f.notna())
    zz = z.dropna()
    q = zz.rolling(window, min_periods=window).quantile(level)
    return q.reindex(df.index).ffill().shift(1)


def _cov(br: np.ndarray) -> dict:
    if not len(br):
        return {"n": 0}
    k, c = kupiec(br, LEVEL), christoffersen(br)
    return {"n": int(len(br)), "breaches": int(br.sum()), "rate": float(br.mean()),
            "kupiec_p": k["p_value"], "christoffersen_p": c["p_value"]}


def run(df: pd.DataFrame, fc: pd.DataFrame, model: str, oos_start_year: int, current_fv: float) -> dict:
    q_ch = rolling_quantile(df, fc, model)
    f = fc[f"{model}_1"]
    q_in = fc[f"q_{model}"]
    rn = df["r_next"]
    ok = (fc.index.year >= oos_start_year) & f.notna() & q_ch.notna() & q_in.notna() & rn.notna()
    br_ch = (rn < q_ch * np.sqrt(f))[ok].to_numpy()
    br_in = (rn < q_in * np.sqrt(f))[ok].to_numpy()
    last = np.zeros(int(ok.sum()), bool)
    last[-756:] = True  # ~ last three years
    z = (rn / np.sqrt(f)).where(f.notna()).dropna()
    q_now = float(np.quantile(z.iloc[-WINDOW:], LEVEL)) if len(z) >= WINDOW else float("nan")
    return {
        "name": f"HAR+VIX variance, quantile of the last {WINDOW} out-of-sample standardized returns, updated daily",
        "registered": "2026-11-23", "window": WINDOW,
        "decision_rule": (f"after >= {MIN_LIVE_DAYS} live days scored for both: recommend switching only if the "
                          "incumbent fails Kupiec or Christoffersen (p < 0.05) and the challenger passes both; "
                          "otherwise keep the incumbent. Owner decides; no automatic switch."),
        "current": {"q": q_now, "var95_1d_simple_ret": float(1 - exp(q_now * sqrt(current_fv))) if np.isfinite(q_now) else None},
        "backtest_context": {
            "note": "context only - the same window was used to find the problem; the decision uses live data",
            "start": str(fc.index[ok][0].date()) if ok.any() else None,
            "full": {"challenger": _cov(br_ch), "incumbent": _cov(br_in)},
            "last_3y": {"challenger": _cov(br_ch[last]), "incumbent": _cov(br_in[last])},
        },
    }


def live_decision(ch: dict, inc: dict) -> str:
    """Apply the registered rule to live summaries on common days."""
    if min(ch.get("n", 0), inc.get("n", 0)) < MIN_LIVE_DAYS:
        return "insufficient"
    passes = lambda s: s["kupiec_p"] >= 0.05 and s["christoffersen_p"] >= 0.05
    if not passes(inc) and passes(ch):
        return "recommend_switch"
    return "keep_incumbent"
