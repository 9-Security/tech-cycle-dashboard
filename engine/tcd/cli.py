"""Command-line entry point.

    python -m tcd refresh --out ../data            # fetch + compute + export
    python -m tcd refresh --offline --out ../data  # reuse cached raw files
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import __version__
from .config import EngineConfig
from .export import build_series, write_all
from .features import build_panel
from .fetch import fetch_all
from .quality import DataQualityError, enforce, run_checks
from .sources.http import FetchError
from .status import build_scenarios, build_status
from dataclasses import replace

from .validation import full_validation, prepare, valuation_comparison

log = logging.getLogger("tcd")


def refresh(args: argparse.Namespace) -> int:
    cfg = EngineConfig()
    t0 = time.time()
    now = datetime.now(timezone.utc)
    run_date = pd.Timestamp(args.run_date) if args.run_date else pd.Timestamp(now.date())
    as_of = now.strftime("%Y%m%dT%H%M%SZ")

    log.info("fetching raw data (offline=%s) into %s", args.offline, args.cache)
    raw = fetch_all(Path(args.cache), cfg, offline=args.offline)
    log.info("building PIT monthly panel")
    panel = build_panel(raw, cfg.features)
    bt = prepare(panel, cfg.backtest)

    checks = run_checks(raw, panel, bt, run_date,
                        max_staleness_days=10_000 if args.allow_stale else args.max_staleness_days)
    for c in checks:
        (log.warning if c.status != "PASS" else log.info)("DQ %-22s %s  %s", c.name, c.status, c.detail)
    enforce(checks)

    complete = panel[~panel["partial"].astype(bool)]
    panel_end = complete.index[-1]
    live_year = (panel_end + pd.offsets.MonthEnd(1)).year
    log.info("nested walk-forward over %d configs (live year %d)", len(cfg.grid), live_year)
    vrun = full_validation(bt, cfg.grid, cfg.backtest, live_year)
    params = vrun.wf.live_params

    alt_mode = "price_ext" if cfg.features.valuation == "pe" else "pe"
    alt_panel = build_panel(raw, replace(cfg.features, valuation=alt_mode))
    vrun.report["valuation_comparison"] = valuation_comparison(
        {cfg.features.valuation: panel, alt_mode: alt_panel}, cfg.grid, cfg.backtest, live_year)

    status = build_status(panel, params, live_year)
    git_sha = os.environ.get("GITHUB_SHA", "")[:12] or None
    meta = {
        "as_of": as_of,
        "DATA_SOURCE": "REAL",
        "data_source": "REAL",
        "engine_version": __version__,
        "git_sha": git_sha,
        "n_months": int(len(vrun.wf.dates)),
        "panel_start": str(vrun.wf.dates[0].date()),
    }
    status = {**meta, **status, "metrics": vrun.report["oos"],
              "metrics_basis": "nested walk-forward out-of-sample",
              "snapshot_label": "Live - refreshed daily"}
    scenarios = {**meta, "panel_end": status["panel_end"], "regime": status["regime"],
                 "signals": status["signals"], "weights": status["weights"],
                 **build_scenarios(status, params), "snapshot_label": "Live - rule-based brief"}

    validation = {**meta, **vrun.report, "config": cfg.to_dict()}
    last_obs = pd.Timestamp(panel.attrs["last_obs"])
    health = {
        "ok": True,
        "mode": "live",
        "as_of": as_of,
        "run_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine_version": __version__,
        "git_sha": git_sha,
        "panel_end": status["panel_end"],
        "data_through": str(last_obs.date()),
        "runtime_s": round(time.time() - t0, 1),
        "checks": [c.to_dict() for c in checks],
        "sources": {
            "XLK": str(raw.xlk.index.max().date()),
            "^NDX": str(raw.ndx.index.max().date()),
            "VIX": str(raw.vix.index.max().date()),
            **{f"FRED {k}": str(v.index.max().date()) for k, v in raw.fred.items()},
            **{f"SEC {t}": str(f["capex"]["filed"].max().date()) for t, f in raw.sec_facts.items() if not f["capex"].empty},
        },
        "raw_manifest": raw.manifest,
        "label": "Live - GitHub Actions daily refresh",
    }
    prov = status.get("provisional") or {}
    history_row = {
        "run_at": as_of,
        "panel_end": status["panel_end"],
        "regime": status["regime"]["label"],
        "executed_weight": status["weights"]["executed_weight"],
        "provisional_month": prov.get("month"),
        "provisional_regime": (prov.get("regime") or {}).get("label"),
        "provisional_weight": prov.get("next_month_weight_if_month_ended_today"),
        "vix": (prov.get("signals") or status["signals"])["vix"],
        "overheat_score": (prov.get("signals") or status["signals"])["overheat_score"],
        "earn_score": (prov.get("signals") or status["signals"])["earn_score"],
        "oos_sharpe": round(vrun.report["oos"]["sharpe"], 4),
        "git_sha": git_sha,
    }
    for k in ("vix", "overheat_score", "earn_score"):
        if history_row[k] is not None:
            history_row[k] = round(history_row[k], 4)

    series = build_series(vrun, panel, as_of)
    written = write_all(Path(args.out), series=series, status=status, scenarios=scenarios,
                        validation=validation, health=health, panel=panel, history_row=history_row)
    log.info("wrote %d files to %s in %.1fs", len(written), args.out, time.time() - t0)
    log.info("regime %s | weight %.2f | OOS Sharpe %.2f | BH Sharpe %.2f",
             status["regime"]["label"], status["weights"]["executed_weight"],
             vrun.report["oos"]["sharpe"], vrun.report["bh"]["sharpe"])
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tcd", description="Tech Capex-cycle regime engine")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("refresh", help="fetch data, run walk-forward, export dashboard JSON")
    r.add_argument("--out", default="../data", help="dashboard data directory")
    r.add_argument("--cache", default=".cache/raw", help="raw download cache")
    r.add_argument("--offline", action="store_true", help="use cached raw files only")
    r.add_argument("--allow-stale", action="store_true", help="skip market freshness gate (backfills/tests)")
    r.add_argument("--max-staleness-days", type=int, default=7)
    r.add_argument("--run-date", help="override run date (YYYY-MM-DD) for freshness checks")
    r.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        return refresh(args)
    except (FetchError, DataQualityError) as exc:
        log.error("refresh aborted, outputs left untouched: %s", exc)
        return 2
    except Exception:
        log.exception("refresh crashed, outputs left untouched")
        return 1


if __name__ == "__main__":
    sys.exit(main())
