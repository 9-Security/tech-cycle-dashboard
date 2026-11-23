"""Plain-language daily risk light.

Rule (fixed, documented on the dashboard):
    green   tomorrow's volatility forecast below the historical median
    yellow  between the 50th and 80th percentile
    red     at or above the 80th percentile
The percentile compares the HAR + VIX next-day forecast with every day's
22-day realized volatility since the start of the series, using only data
up to the latest close.

Only codes and numbers are produced here; the dashboard renders the
sentences in the reader's language from these fields.
"""

from __future__ import annotations

import math

import pandas as pd

LEVELS = (("green", 0.50), ("yellow", 0.80), ("red", 1.01))


def level_for(percentile: float) -> str:
    for name, upper in LEVELS:
        if percentile < upper:
            return name
    return "red"


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def valuation_state(val_z: float | None) -> str:
    if val_z is None:
        return "unknown"
    return "below" if val_z < -0.5 else "above" if val_z > 0.5 else "near"


def earnings_state(score: float | None, threshold: float = -1.0) -> str:
    if score is None:
        return "unknown"
    return "weakening" if score < threshold else "growing" if score > 0.5 else "flat"


def build_light(short_current: dict, panel: pd.DataFrame) -> dict:
    pctl = short_current["vol_hist_percentile"]
    latest = panel.iloc[-1]  # partial (month-to-date) row if a month is in progress
    partial = bool(latest.get("partial", False))
    val_z = _f(latest.get("val_z"))
    return {
        "level": level_for(pctl),
        "rule": {"green_below": LEVELS[0][1], "red_at_or_above": LEVELS[1][1],
                 "basis": "HAR + VIX next-day vol forecast vs history of 22-day realized vol"},
        "date": short_current["date"],
        "vol_percentile": pctl,
        "vol_ann": short_current["vol_1d_ann"],
        "vol_median": short_current["vol_hist_median"],
        "vol_ratio": short_current["vol_1d_ann"] / short_current["vol_hist_median"],
        "daily_move": short_current["vol_1d"],
        "var95": short_current["var95_1d_simple_ret"],
        "hist_start": short_current["vol_hist_start"],
        "mtd_month": panel.index[-1].strftime("%Y-%m") if partial else None,
        "mtd_return": _f(latest.get("risk_ret")) if partial else None,
        "pe": _f(latest.get("pe_level", latest.get("pe_agg"))),
        "val_z": val_z,
        "val_state": valuation_state(val_z if latest.get("val_src") == "PE" else None),
        "earn_score": _f(latest.get("earn_score")),
        "earn_state": earnings_state(_f(latest.get("earn_score"))),
    }
