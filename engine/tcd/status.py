"""Live posture (what is in force now, what the in-progress month implies)
and rule-based scenario briefs. No forecasting model: scenarios are
'what would flip the regime' statements derived from live parameters."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import REGIME_LABELS, RegimeParams
from .regime import classify_arrays, weights_for


def _row_regime(row: pd.Series, p: RegimeParams) -> tuple[int, float]:
    code = int(classify_arrays(
        np.array([row["vix"]]), np.array([row["overheat_score"]]), np.array([row["earn_score"]]), p
    )[0])
    return code, float(weights_for(np.array([code]), p)[0])


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _signals(row: pd.Series) -> dict:
    return {
        "vix": _f(row["vix"]),
        "vix_last": _f(row.get("vix_last")),
        "overheat_score": _f(row["overheat_score"]),
        "val_z": _f(row["val_z"]),
        "capex_z": _f(row["capex_z"]),
        "capex_ratio_firm": _f(row.get("capex_ratio_firm")),
        "capex_src": row.get("capex_src"),
        "earn_score": _f(row["earn_score"]),
        "earn_src": row.get("earn_src"),
        "shock_flag": None,
    }


def build_status(panel: pd.DataFrame, params: RegimeParams, params_year: int) -> dict:
    complete = panel[~panel["partial"].astype(bool)]
    last = complete.iloc[-1]
    panel_end = complete.index[-1]
    code, w = _row_regime(last, params)
    sig = _signals(last)
    sig["shock_flag"] = int(code == 2)

    in_force_month = (panel_end + pd.offsets.MonthEnd(1)).strftime("%Y-%m")
    out = {
        "panel_end": str(panel_end.date()),
        "regime": {"code": code, "label": REGIME_LABELS[code]},
        "signals": sig,
        "weights": {
            "executed_weight": w,
            "recommended_weight": w,
            "in_force_month": in_force_month,
            "note": f"Risk weight decided at {panel_end.date()} month-end and held through {in_force_month} (lag-1).",
        },
        "params": {**params.to_dict(), "fit_for_year": params_year},
        "provisional": None,
    }

    if bool(panel["partial"].iloc[-1]):
        prow = panel.iloc[-1]
        pcode, pw = _row_regime(prow, params)
        psig = _signals(prow)
        psig["shock_flag"] = int(pcode == 2)
        out["provisional"] = {
            "month": panel.index[-1].strftime("%Y-%m"),
            "data_through": str(pd.Timestamp(panel.attrs["last_obs"]).date()),
            "regime": {"code": pcode, "label": REGIME_LABELS[pcode]},
            "signals": psig,
            "next_month_weight_if_month_ended_today": pw,
            "note": "Month-to-date signals. Not final until month-end; not used in the backtest.",
        }
        out["weights"]["target_weight"] = pw
    else:
        out["weights"]["target_weight"] = w
    return out


def build_scenarios(status: dict, params: RegimeParams) -> dict:
    src = status["provisional"] or status
    s = src["signals"]
    cur = src["regime"]["label"]
    p = params

    def dist(v, thr, above=True):
        if v is None:
            return None
        return (thr - v) if above else (v - thr)

    d_vix = dist(s["vix"], p.vix_threshold)
    d_oh = dist(s["overheat_score"], p.overheat_threshold)
    d_earn = dist(s["earn_score"], p.earn_threshold, above=False)

    def fmt(x, nd=2):
        return "n/a" if x is None else f"{x:.{nd}f}"

    triggers = [
        {"id": "shock", "signal": "VIX (monthly mean)", "value": s["vix"], "threshold": p.vix_threshold,
         "direction": "above", "distance": d_vix, "active": d_vix is not None and d_vix < 0, "weight": p.w_shock},
        {"id": "overheat", "signal": "Overheat score", "value": s["overheat_score"], "threshold": p.overheat_threshold,
         "direction": "above", "distance": d_oh, "active": d_oh is not None and d_oh < 0, "weight": p.w_overheat},
        {"id": "digestion", "signal": "Earnings momentum score", "value": s["earn_score"], "threshold": p.earn_threshold,
         "direction": "below", "distance": d_earn, "active": d_earn is not None and d_earn < 0, "weight": p.w_digestion},
    ]

    scenarios = [
        {
            "id": "base",
            "horizon": "1-3 months",
            "thesis": f"Signals stay on their current side of every threshold; regime remains {cur}.",
            "flip_conditions": [
                f"VIX {fmt(s['vix'])} vs Shock threshold {fmt(p.vix_threshold)}",
                f"Overheat {fmt(s['overheat_score'])} vs threshold {fmt(p.overheat_threshold)}",
                f"Earnings score {fmt(s['earn_score'])} vs Digestion threshold {fmt(p.earn_threshold)}",
            ],
            "suggested_defensive_posture": {
                "risk_weight": status["weights"]["target_weight"],
                "rationale": "Engine weight implied by the latest (provisional if in-progress) signals.",
            },
        },
        {
            "id": "overheat",
            "horizon": "1-3 months",
            "thesis": (f"Overheat trigger already active (score {fmt(s['overheat_score'])} > {fmt(p.overheat_threshold)}); "
                       "it binds whenever Shock is not active." if d_oh is not None and d_oh < 0 else
                       f"Valuation extension + Capex intensity lift the overheat score by {fmt(d_oh)} "
                       f"to cross {fmt(p.overheat_threshold)} while VIX stays below {fmt(p.vix_threshold)}."),
            "flip_conditions": ["Overheat score > threshold", "Shock not active (Shock has priority)"],
            "suggested_defensive_posture": {"risk_weight": p.w_overheat, "rationale": "Overheat defense weight, applied the month after the signal."},
        },
        {
            "id": "shock",
            "horizon": "1-3 months",
            "thesis": (f"Shock trigger already active (monthly-average VIX {fmt(s['vix'])} > {fmt(p.vix_threshold)}); "
                       "Shock overrides every other regime." if d_vix is not None and d_vix < 0 else
                       f"Monthly-average VIX rises {fmt(d_vix)} points to exceed {fmt(p.vix_threshold)}; "
                       "Shock overrides every other regime."),
            "flip_conditions": ["Monthly mean VIX > threshold"],
            "suggested_defensive_posture": {"risk_weight": p.w_shock, "rationale": "Shock defense weight (max de-risking)."},
        },
        {
            "id": "digestion",
            "horizon": "1-3 months",
            "thesis": (f"Digestion trigger already active (earnings score {fmt(s['earn_score'])} < {fmt(p.earn_threshold)})."
                       if d_earn is not None and d_earn < 0 else
                       f"Aggregate TTM earnings momentum drops {fmt(d_earn)} std units to below "
                       f"{fmt(p.earn_threshold)} (Capex digestion / earnings downgrade cycle)."),
            "flip_conditions": ["Earnings score < threshold", "Neither Shock nor Overheat active"],
            "suggested_defensive_posture": {"risk_weight": p.w_digestion, "rationale": "Digestion defense weight."},
        },
    ]

    prov = status["provisional"]
    interp = (
        f"Official regime at {status['panel_end']} month-end: {status['regime']['label']} "
        f"(risk weight {status['weights']['executed_weight']:.2f} held through {status['weights']['in_force_month']}). "
    )
    if prov:
        interp += (
            f"Month-to-date ({prov['month']}, data through {prov['data_through']}) signals point to "
            f"{prov['regime']['label']}; if the month ended today next month's weight would be "
            f"{prov['next_month_weight_if_month_ended_today']:.2f}. "
        )
    interp += (
        f"Parameters were chosen by walk-forward using data through Dec {status['params']['fit_for_year'] - 1} only. "
        "These are rule-based trigger distances, not return forecasts."
    )
    return {
        "mode": "rule_based",
        "interpretation": interp,
        "triggers": triggers,
        "scenarios": scenarios,
        "disclaimer": "Scenario analysis for risk discussion only. Not investment advice. Not an auto-trading signal.",
    }
