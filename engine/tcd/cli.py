"""Command-line entry point.

    python -m tcd refresh --out ../data            # fetch + compute + export
    python -m tcd refresh --offline --out ../data  # reuse cached raw files
"""

from __future__ import annotations

import argparse
import json
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
from . import promotion
from .cross_market import fetch_markets, run_cross_market
from .light import build_light
from .export import clean
from . import ledger, official_check, tw_calendar
from .sources.store import RawStore
from .stocks import StockConfig, fetch_prices as fetch_stock_prices, load_watchlist, merge_stocks, run_stocks
from .risk_model import run_risk
from .short_risk import run_short_risk
from .signal_study import run_study
from .sources.http import FetchError
from .status import build_candidate_status, build_scenarios, build_status
from dataclasses import replace

from .backtest import metrics
from .config import V3_DESIGN_DATE
from .validation import _pick, full_validation, prepare, tilt_spec, valuation_comparison

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

    log.info("v3 candidate: nested walk-forward over %d configs", len(cfg.tilt_grid))
    vrun3 = full_validation(bt, tilt_spec(cfg.tilt_grid), cfg.backtest, live_year)
    design_end = pd.Timestamp(V3_DESIGN_DATE) + pd.offsets.MonthEnd(0)
    post = vrun3.wf.dates > design_end
    since_design = None
    if post.sum() >= 1:
        safe_post = bt.safe[bt.dates > design_end]
        bh_post = vrun3.bh.ret[post]
        since_design = {"months": int(post.sum()),
                        "v3": _pick(metrics(vrun3.wf.sim.ret[post], safe_post)) if post.sum() >= 2 else
                              {"period_return": float(vrun3.wf.sim.ret[post][0])},
                        "bh": _pick(metrics(bh_post, safe_post)) if post.sum() >= 2 else {"period_return": float(bh_post[0])}}
    oos_mask = bt.dates >= vrun3.wf.dates[0]
    promo = promotion.evaluate(
        dates=vrun3.wf.dates, v3_ret=vrun3.wf.sim.ret, bh_ret=vrun3.bh.ret, safe=bt.safe[oos_mask],
        full_v3_sharpe=vrun3.report["oos"]["sharpe"], full_bh_sharpe=vrun3.report["bh"]["sharpe"],
        design_date=V3_DESIGN_DATE, rule=cfg.promotion,
        current_fingerprint=promotion.spec_fingerprint(cfg.tilt_grid, cfg.features, cfg.backtest),
        max_gap_days=promotion.refresh_gaps(Path(args.out) / "history.csv",
                                            pd.Timestamp(V3_DESIGN_DATE), pd.Timestamp(now.date())),
    )
    log.info("v3 promotion rule: %s - %s", promo["state"], promo["note"])
    # Weight in force now = v3 target at the last complete month (lag-1, after band).
    cand_now = float(vrun3.wf.target[-1])

    status = build_status(panel, params, live_year)
    status["candidate"] = build_candidate_status(panel, vrun3.wf.live_params, live_year, cand_now,
                                                 V3_DESIGN_DATE, since_design)
    status["candidate"]["promotion"] = {"state": promo["state"], "note": promo["note"], "months": promo["months"],
                                        "earliest_decision_after": promo["earliest_decision_after"]}
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

    m2, m3 = vrun.report["oos"], vrun3.report["oos"]
    validation = {**meta, **vrun.report, "config": cfg.to_dict(),
                  "candidate": {**vrun3.report, "design_date": V3_DESIGN_DATE, "since_design": since_design,
                                "promotion": promo},
                  "model_comparison": [
                      {"model": "regime_v2", "label": "v2 regime (live)", **m2},
                      {"model": "tilt_v3", "label": "v3 tilt + vol target (candidate)", **m3},
                      {"model": "buy_hold", "label": "Buy & hold", **vrun.report["bh"]},
                      {"model": "vol_matched_bh_v3", "label": "Vol-matched B&H (to v3, ex-post)", **vrun3.report["vol_matched_bh"]},
                  ]}
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
        "v3_weight": round(status["candidate"]["executed_weight"], 4),
        "v3_month_end_weight": round(status["candidate"]["month_end"]["weight"], 4),
        "git_sha": git_sha,
    }
    for k in ("vix", "overheat_score", "earn_score"):
        if history_row[k] is not None:
            history_row[k] = round(history_row[k], 4)

    # Out-of-domain test of the frozen v3 design (pre-registered; report only).
    # A fetch problem here must not block the daily refresh.
    cross = None
    try:
        mprices, mmanifest, mwarn = fetch_markets(Path(args.cache), args.offline, cfg.fetch.timeout_s, cfg.fetch.retries)
        cross = {**meta, **run_cross_market(mprices, raw.vix, raw.fred["tbill_3m"], panel, cfg.features, cfg.backtest, cfg.tilt_grid),
                 "fetch_warnings": mwarn, "raw_manifest": mmanifest}
        log.info("cross-market v3 test: overall_pass=%s (%s)", cross["verdict"]["overall_pass"], cross["verdict"]["C1"]["detail"])
    except Exception as exc:  # noqa: BLE001 - report-only block
        log.warning("cross-market test skipped: %s", exc)

    # Per-stock risk monitoring (report only; never blocks the refresh).
    stocks = stocks_fresh = stocks_prices = None
    try:
        wl = load_watchlist()
        syms = [x["symbol"] for x in wl["stocks"]] + [b for b in wl["benchmarks"].values() if b != "^NDX"]
        sprices, smanifest, swarn = fetch_stock_prices(Path(args.cache), args.offline, cfg.fetch.timeout_s, cfg.fetch.retries,
                                                       syms, already_fetched=set(raw.prices))
        sprices["^NDX"] = raw.ndx
        raw_sprices = sprices  # unmodified Yahoo bars: audited by the second-source check
        sprices, cal = tw_calendar.clean(sprices, wl)
        fresh = {**meta, **run_stocks(sprices, raw, wl), "fetch_warnings": swarn, "raw_manifest": smanifest,
                 "data_cleaning": {"tw_holiday_bars": cal}}
        stocks = merge_stocks(_read_json(Path(args.out) / "stocks.json"), fresh, ("US", "TW"), wl, as_of)
        log.info("stocks: %d analysed, %d verified VaR, skipped %s", len(stocks["stocks"]),
                 sum(r["backtest"]["verified"] for r in stocks["stocks"]), stocks["skipped"])
        stocks_fresh, stocks_prices = fresh["stocks"], sprices
    except Exception as exc:  # noqa: BLE001 - report-only block
        log.warning("stock monitoring skipped: %s", exc)

    signals = {**meta, **run_study(panel)}
    risk = {**meta, **run_risk(panel)}
    risk["short_term"] = run_short_risk(raw)
    primary = risk["targets"][0]
    skill = primary["verdict"].startswith("skillful")
    cur = primary["current"].get("provisional") or primary["current"]["month_end"]
    status["risk"] = {
        "target": primary["label"],
        "verdict": primary["verdict"],
        "headline_source": "model" if skill else "base_rate",
        "headline_p": cur["p"] if skill else primary["current"]["base_rate"],
        "base_rate": primary["current"]["base_rate"],
        "model_p": cur["p"],
        "model_ci90": cur["ci90"],
        "as_of_row": cur["date"],
        "vol_forecast_next_month": (risk["vol_forecast"]["current"].get("provisional")
                                    or risk["vol_forecast"]["current"]["month_end"]),
        "vol_forecast_oos_r2": risk["vol_forecast"]["oos_r2_vs_mean"],
        "short_term": risk["short_term"]["current"],
        "short_term_epu_verdict": risk["short_term"]["epu_verdict"],
    }
    status["light"] = build_light(risk["short_term"]["current"], panel)
    history_row["light"] = status["light"]["level"]
    history_row["p_dd20_12m_model"] = round(cur["p"], 4)
    history_row["vol_fcst_next_month"] = round(status["risk"]["vol_forecast_next_month"]["vol"], 4)
    history_row["var95_1d"] = round(risk["short_term"]["current"]["var95_1d_simple_ret"], 5)
    series = build_series(vrun, panel, as_of, candidate=vrun3)
    written = write_all(Path(args.out), series=series, status=status, scenarios=scenarios,
                        validation=validation, health=health, panel=panel, history_row=history_row,
                        signals=signals, risk=risk, cross_market=cross, stocks=stocks)
    if stocks_prices is not None:
        _official(args, raw_sprices, wl, as_of, cfg)
    if stocks_fresh is not None:
        try:  # live forecast ledger + reconciliation (report only)
            ledger.update(Path(args.out), stocks_fresh, stocks_prices, ("US", "TW"), as_of,
                          datetime.now(timezone.utc), __version__, StockConfig(), all_rows=stocks["stocks"])
        except Exception as exc:  # noqa: BLE001
            log.error("forecast ledger not updated: %s", exc)
    log.info("wrote %d files to %s in %.1fs", len(written), args.out, time.time() - t0)
    log.info("v2 regime %s | weight %.2f | OOS Sharpe %.2f | BH Sharpe %.2f",
             status["regime"]["label"], status["weights"]["executed_weight"],
             vrun.report["oos"]["sharpe"], vrun.report["bh"]["sharpe"])
    log.info("v3 candidate weight %.2f | OOS Sharpe %.2f", cand_now, vrun3.report["oos"]["sharpe"])
    return 0


def _read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write_json_atomic(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(clean(obj), indent=1, allow_nan=False, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def _official(args, prices: dict, wl: dict, as_of: str, cfg: EngineConfig,
              markets: tuple[str, ...] = ("US", "TW")) -> None:
    """Second-source close check: TW vs TWSE / TPEx, US vs Nasdaq (report only, never blocks)."""
    try:
        store = RawStore(Path(args.cache) / "official", offline=args.offline, timeout=cfg.fetch.timeout_s, retries=1)
        res = official_check.run(prices, wl, store, as_of, markets=markets)
        path = Path(args.out) / "official_check.json"
        res = official_check.merge(_read_json(path), res, markets, wl)
        _write_json_atomic(path, res)
        log.info("second-source close check %s: %s", "/".join(markets), res["summary_by_market"])
    except Exception as exc:  # noqa: BLE001
        log.error("official close check skipped: %s", exc)


def stocks_refresh(args: argparse.Namespace) -> int:
    """Refresh only the stocks of one market (e.g. Taiwan after its close) and
    merge them into data/stocks.json; everything else is left untouched."""
    now = datetime.now(timezone.utc)
    as_of = now.strftime("%Y%m%dT%H%M%SZ")
    markets = (args.market,)
    wl = load_watchlist()
    syms = [x["symbol"] for x in wl["stocks"] if x["market"] in markets] + [wl["benchmarks"][m] for m in markets]
    cfg = EngineConfig()
    prices, manifest, warns = fetch_stock_prices(Path(args.cache), args.offline, cfg.fetch.timeout_s, cfg.fetch.retries, syms)
    for w in warns:
        log.warning("fetch: %s", w)
    raw_prices = prices
    cal = None
    if "TW" in markets:
        prices, cal = tw_calendar.clean(prices, wl)
    fresh = run_stocks(prices, None, wl, markets=markets)
    if cal is not None:
        fresh["data_cleaning"] = {"tw_holiday_bars": cal}
    if not fresh["stocks"]:
        log.error("no %s stock could be analysed; outputs left untouched", args.market)
        return 2
    out = Path(args.out) / "stocks.json"
    existing = _read_json(out)
    meta = {"as_of": as_of, "engine_version": __version__, "git_sha": os.environ.get("GITHUB_SHA", "")[:12] or None}
    merged = merge_stocks(existing, {**meta, **fresh, "fetch_warnings": warns,
                                     "raw_manifest": {**(existing or {}).get("raw_manifest", {}), **manifest}},
                          markets, wl, as_of)
    _write_json_atomic(out, merged)
    _official(args, raw_prices, wl, as_of, cfg, markets)
    try:
        ledger.update(Path(args.out), fresh["stocks"], prices, markets, as_of, now, __version__, StockConfig(),
                      all_rows=merged["stocks"])
    except Exception as exc:  # noqa: BLE001
        log.error("forecast ledger not updated: %s", exc)
    log.info("stocks %s: %d analysed, %d verified, skipped %s", args.market, len(fresh["stocks"]),
             sum(r["backtest"]["verified"] for r in fresh["stocks"]), fresh["skipped"])
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
    st = sub.add_parser("stocks", help="refresh one market's stocks only and merge into stocks.json")
    st.add_argument("--market", choices=["TW", "US"], required=True)
    st.add_argument("--out", default="../data")
    st.add_argument("--cache", default=".cache/raw")
    st.add_argument("--offline", action="store_true")
    st.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        if args.cmd == "stocks":
            return stocks_refresh(args)
        return refresh(args)
    except (FetchError, DataQualityError) as exc:
        log.error("refresh aborted, outputs left untouched: %s", exc)
        return 2
    except Exception:
        log.exception("refresh crashed, outputs left untouched")
        return 1


if __name__ == "__main__":
    sys.exit(main())
