"""Status of the pre-registered v2 -> v3 promotion rule (report only).

See docs/model-promotion.md. Nothing here changes the live model.
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import metrics
from .config import BacktestConfig, FeatureConfig, PromotionRule, TiltGrid
from .validation import sharpe_diff_test

SPEC_SOURCES = ("model_tilt.py", "features.py", "fundamentals.py", "backtest.py")


def spec_fingerprint(tilt_grid: TiltGrid, features: FeatureConfig, backtest: BacktestConfig) -> str:
    """sha256 over v3's configuration values and the source of the modules it depends on."""
    h = hashlib.sha256()
    cfg = {"tilt_grid": asdict(tilt_grid), "features": asdict(features), "backtest": asdict(backtest)}
    h.update(json.dumps(cfg, sort_keys=True, default=str).encode())
    here = Path(__file__).resolve().parent
    for name in SPEC_SOURCES:
        h.update(name.encode())
        h.update((here / name).read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def refresh_gaps(history_csv: Path, start: pd.Timestamp, now: pd.Timestamp) -> int | None:
    """Longest gap (days) between successful runs in [start, now], counting `now`."""
    if not history_csv.exists():
        return None
    with history_csv.open(newline="") as fh:
        runs = [pd.Timestamp(r["run_at"][:8]) for r in csv.DictReader(fh) if r.get("run_at")]
    runs = sorted({d for d in runs if d >= start} | {now.normalize()})
    if len(runs) < 2:
        return 0
    return int(max((b - a).days for a, b in zip(runs, runs[1:])))


def evaluate(*, dates: pd.DatetimeIndex, v3_ret: np.ndarray, bh_ret: np.ndarray, safe: np.ndarray,
             full_v3_sharpe: float, full_bh_sharpe: float, design_date: str, rule: PromotionRule,
             current_fingerprint: str, max_gap_days: int | None) -> dict:
    design_end = pd.Timestamp(design_date) + pd.offsets.MonthEnd(0)
    post = dates > design_end
    n = int(post.sum())
    first_month = (design_end + pd.offsets.MonthEnd(1)).strftime("%Y-%m")
    earliest = (design_end + pd.offsets.MonthEnd(rule.min_months)).strftime("%Y-%m")
    out = {"design_date": design_date, "first_month": first_month, "months": n,
           "min_months": rule.min_months, "earliest_decision_after": earliest,
           "retire_after": (design_end + pd.offsets.MonthEnd(rule.retire_months)).strftime("%Y-%m"),
           "criteria": [], "post_window": None}

    crit = out["criteria"]
    crit.append({"id": "C1", "name": f"At least {rule.min_months} post-design months", "pass": n >= rule.min_months,
                 "detail": f"{n}/{rule.min_months}"})
    if n >= 2:
        mv, mb = metrics(v3_ret[post], safe[post]), metrics(bh_ret[post], safe[post])
        c = min(1.0, mv["ann_vol"] / mb["ann_vol"]) if mb["ann_vol"] > 0 else 1.0
        vm_ret = c * bh_ret[post] + (1 - c) * safe[post]
        mvm = metrics(vm_ret, safe[post])
        out["post_window"] = {"v3": mv, "bh": mb, "vol_matched_bh": {**mvm, "risk_fraction": c},
                              "sharpe_diff_vs_bh": sharpe_diff_test(v3_ret[post], bh_ret[post], safe[post])}
        crit.append({"id": "C2", "name": "v3 Sharpe > vol-matched B&H Sharpe (post-design)",
                     "pass": mv["sharpe"] > mvm["sharpe"], "detail": f"{mv['sharpe']:.2f} vs {mvm['sharpe']:.2f}"})
        crit.append({"id": "C3", "name": f"v3 Max DD no worse than vol-matched B&H by > {rule.mdd_tolerance:.0%}",
                     "pass": mv["max_dd"] >= mvm["max_dd"] - rule.mdd_tolerance,
                     "detail": f"{mv['max_dd']:.1%} vs {mvm['max_dd']:.1%}"})
    else:
        crit.append({"id": "C2", "name": "v3 Sharpe > vol-matched B&H Sharpe (post-design)", "pass": None, "detail": "needs >= 2 months"})
        crit.append({"id": "C3", "name": f"v3 Max DD no worse than vol-matched B&H by > {rule.mdd_tolerance:.0%}", "pass": None, "detail": "needs >= 2 months"})
    crit.append({"id": "C4", "name": "Full OOS history (2000+): v3 Sharpe >= B&H Sharpe",
                 "pass": full_v3_sharpe >= full_bh_sharpe, "detail": f"{full_v3_sharpe:.2f} vs {full_bh_sharpe:.2f}"})
    crit.append({"id": "C5", "name": "v3 specification unchanged since design date",
                 "pass": current_fingerprint == rule.spec_fingerprint,
                 "detail": "fingerprint matches" if current_fingerprint == rule.spec_fingerprint
                 else f"changed ({current_fingerprint[:12]} != {rule.spec_fingerprint[:12]}): reset design date"})
    crit.append({"id": "C6", "name": f"No gap > {rule.max_refresh_gap_days} days between successful daily refreshes",
                 "pass": None if max_gap_days is None else max_gap_days <= rule.max_refresh_gap_days,
                 "detail": "no history" if max_gap_days is None else f"longest gap {max_gap_days} d"})

    others = [c["pass"] for c in crit if c["id"] != "C1"]
    if not crit[0]["pass"]:
        state = "collecting"
        note = f"Collecting post-design evidence: {n}/{rule.min_months} months. No decision before {earliest}."
    elif all(p is True for p in others):
        state = "eligible"
        note = "All criteria met. Promotion is eligible; the owner decides. The engine does not switch automatically."
    elif n >= rule.retire_months:
        state = "retire"
        note = f"Criteria still not met after {rule.retire_months} months: retire the v3 candidate (or re-design with a new design date)."
    else:
        state = "not_met"
        note = f"Minimum period reached but criteria not met; keep collecting until {out['retire_after']}."
    if crit[4]["pass"] is False:
        state, note = "invalid", "v3 specification changed after the design date: the evaluation clock must be reset."
    out["state"], out["note"] = state, note
    return out
