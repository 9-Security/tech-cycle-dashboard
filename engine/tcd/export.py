"""Write dashboard artifacts. All files are staged then swapped in together."""

from __future__ import annotations

import csv
import json
import math
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from .config import REGIME_COLORS, REGIME_LABELS

PANEL_COLUMNS = [
    "risk_ret", "risk_src", "safe_ret", "tbill_pct", "vix", "vix_last", "val_ext", "val_z",
    "capex_ratio_proxy", "capex_z_proxy", "capex_ratio_firm", "n_capex_names", "capex_z_firm",
    "capex_z", "capex_src", "earn_g_firm", "earn_score_firm", "earn_g_proxy", "earn_score_proxy",
    "earn_score", "earn_src", "n_earn_names", "overheat_score", "partial",
]

HISTORY_FIELDS = [
    "run_at", "panel_end", "regime", "executed_weight", "provisional_month", "provisional_regime",
    "provisional_weight", "vix", "overheat_score", "earn_score", "oos_sharpe", "git_sha",
]


def clean(obj):
    """JSON-safe: NaN/inf -> None, numpy scalars -> Python."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj.date())
    return obj


def _r(a, nd=6) -> list:
    return [None if (x is None or not np.isfinite(x)) else round(float(x), nd) for x in np.asarray(a, float)]


def regime_spans(dates: pd.DatetimeIndex, codes: np.ndarray) -> list[dict]:
    spans = []
    start = 0
    for i in range(1, len(codes) + 1):
        if i == len(codes) or codes[i] != codes[start]:
            c = int(codes[start])
            spans.append({"regime": c, "label": REGIME_LABELS[c], "color": REGIME_COLORS[c],
                          "start": str(dates[start].date()), "end": str(dates[i - 1].date())})
            start = i
    return spans


def build_series(vrun, panel: pd.DataFrame, as_of: str) -> dict:
    wf = vrun.wf
    dates = wf.dates
    p = panel.reindex(dates)
    is_nav = np.cumprod(1.0 + vrun.insample_ret_oos)
    rep = vrun.report
    return {
        "source": "Nested walk-forward OOS - Yahoo (XLK/^NDX/^VIX) + FRED + SEC XBRL",
        "snapshot_label": "Live - refreshed daily by GitHub Actions",
        "as_of": as_of,
        "dates": [str(d.date()) for d in dates],
        "strategy_nav": _r(wf.sim.nav),
        "benchmark_nav": _r(vrun.bh.nav),
        "insample_nav": _r(is_nav),
        "regime": [int(c) for c in wf.codes],
        "regime_spans": regime_spans(dates, wf.codes),
        "vix": _r(p["vix"], 2),
        "overheat_score": _r(p["overheat_score"], 4),
        "earn_score": _r(p["earn_score"], 4),
        "capex_ratio_firm": _r(p["capex_ratio_firm"], 4),
        "capex_src": list(p["capex_src"].astype(str)),
        "risk_weight": _r(wf.executed, 4),
        "target_weight": _r(wf.target, 4),
        "metrics": {**rep["oos"], "bh_final_nav": rep["bh"]["final_nav"], "bh_sharpe": rep["bh"]["sharpe"],
                    "bh_max_dd": rep["bh"]["max_dd"], "insample_sharpe": rep["insample_best"]["on_oos_window"]["sharpe"]},
        "regime_labels": {str(k): v for k, v in REGIME_LABELS.items()},
        "regime_colors": {str(k): v for k, v in REGIME_COLORS.items()},
    }


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(clean(obj), indent=1, allow_nan=False, ensure_ascii=False) + "\n")


def write_all(out_dir: Path, *, series: dict, status: dict, scenarios: dict, validation: dict,
              health: dict, panel: pd.DataFrame, history_row: dict) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=out_dir))
    try:
        _write_json(stage / "series.json", series)
        _write_json(stage / "status.json", status)
        _write_json(stage / "scenarios.json", scenarios)
        _write_json(stage / "validation.json", validation)
        _write_json(stage / "health.json", health)

        cols = [c for c in PANEL_COLUMNS if c in panel.columns]
        panel[cols].round(6).to_csv(stage / "panel_monthly.csv", date_format="%Y-%m-%d")

        hist = out_dir / "history.csv"
        rows = []
        if hist.exists():
            with hist.open(newline="") as fh:
                rows = [r for r in csv.DictReader(fh)]
        # One row per UTC run date; a re-run on the same day replaces it.
        day = history_row["run_at"][:8]
        rows = [r for r in rows if not r.get("run_at", "").startswith(day)]
        rows.append({k: ("" if history_row.get(k) is None else history_row.get(k)) for k in HISTORY_FIELDS})
        with (stage / "history.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=HISTORY_FIELDS)
            w.writeheader()
            w.writerows(rows)

        written = []
        for f in sorted(stage.iterdir()):
            dest = out_dir / f.name
            os.replace(f, dest)
            written.append(dest)
        return written
    finally:
        shutil.rmtree(stage, ignore_errors=True)
