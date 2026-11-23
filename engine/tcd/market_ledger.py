"""Live forecast ledger for the MARKET-level risk numbers (methodology section 17).

The stock ledger (ledger.py) covers single names. The market numbers the site
trusts most - the 1-day 95% VaR, the 5-day volatility and the next-month
volatility forecast - were only kept in history.csv, which a same-day re-run
overwrites. This module gives them the same treatment as the stock ledger:

  * data/forecasts/market_ledger.csv - append-only, key (target, origin_date),
    first write wins, existing bytes verified unchanged;
      var_1d  1-day 95% VaR (simple return), HAR and EWMA next-day variance,
              risk light of that day; origin = last daily bar, logged only once
              the US close is final;
      vol_5d  average daily variance over the next 5 trading days (HAR, EWMA);
      vol_1m  next-month realized volatility (annualized, 21 trading days) with
              its 90% band; origin = a COMPLETE month-end only (provisional
              mid-month forecasts are not logged).
  * data/forecasts/market_outcomes.csv - each forecast scored against the risk
    asset (XLK adjusted close, the series the models use); final outcomes are
    frozen, pending ones re-evaluated.
  * data/forecast_review_market.json - summary per target for the current
    model only, with pre-registered minimum samples (no verdict before them):
    var_1d 250 scored days (Kupiec + Christoffersen); vol_1m 24 months.

Nothing here feeds back into the models.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from math import sqrt
from pathlib import Path

import numpy as np
import pandas as pd

from . import exposure, risk_model, sequential, short_risk, var_challenger, var_panel
from .ledger import FINAL_STATUSES, _atomic_write, append_ledger, bar_is_final
from .short_risk import christoffersen, diebold_mariano, kupiec, qlike

log = logging.getLogger(__name__)

COLUMNS = ["target", "origin_date", "issued_at", "var95", "har_var", "ewma_var", "vol_ann", "band_lo", "band_hi",
           "level", "engine_version", "model_id"]
OUTCOME_COLUMNS = ["target", "origin_date", "target_end", "status", "realized", "breach", "var95", "har_var",
                   "ewma_var", "vol_ann", "band_lo", "band_hi", "qlike_har", "qlike_ewma", "ratio", "log_error",
                   "in_band", "level", "model_id"]
CAP_OVERSHOOT = 1.5  # capped realized 5-day vol above 1.5x target counts as an overshoot

STR = {"target": str, "origin_date": str, "target_end": str, "status": str, "level": str, "model_id": str,
       "issued_at": str, "engine_version": str}


@dataclass(frozen=True)
class MarketReviewConfig:
    var_level: float = 0.05
    min_days_var: int = 250      # 1-day VaR verdict (Kupiec + Christoffersen)
    min_months_vol: int = 24     # next-month volatility verdict
    rolling_days: int = 60


def _fp(funcs, cfg_dict: dict, extra: str = "") -> str:
    blob = "".join(inspect.getsource(f) for f in funcs).encode() + json.dumps(cfg_dict, sort_keys=True).encode()
    return hashlib.sha256(blob + extra.encode()).hexdigest()[:12]


def _variance_fp(live_model: str) -> str:
    """The daily variance forecast shared by the incumbent VaR, the challenger
    and the 5-day volatility: code path, module constants and config."""
    f = [short_risk.daily_frame, short_risk.design, short_risk.fit_var, short_risk.VarModel, short_risk._ols,
         short_risk.walk_forward]
    consts = repr((short_risk.FEATURES, sorted(short_risk.LOGGED)))
    return _fp(f, asdict(short_risk.ShortRiskConfig()), live_model + consts)


def short_model_id(live_model: str) -> str:
    """Incumbent 1-day VaR and 5-day volatility: variance + its own quantile rule."""
    return _fp([short_risk.oos_quantile, short_risk.current], {}, _variance_fp(live_model))


def challenger_model_id(live_model: str) -> str:
    """Challenger: same variance + the registered rolling quantile only (not the
    incumbent's quantile code, not the backtest code)."""
    return _fp([var_challenger.rolling_quantile], {"window": var_challenger.WINDOW, "level": var_challenger.LEVEL},
               _variance_fp(live_model))


def exposure_model_id(live_model: str) -> str:
    """Exposure cap (exposure.py): rule code and constants + the 5-day variance
    forecast it divides by (short_risk.current also computes the target)."""
    consts = repr((exposure.STEP, exposure.BANDS))
    return _fp([exposure.cap_for, exposure.band_for, exposure.current, short_risk.current], {},
               consts + _variance_fp(live_model))


def panel_model_id() -> str:
    """Multi-market panel (var_panel.py): its own frame / walk-forward / quantile
    code, the shared HAR fitting code and constants."""
    f = [var_panel.frame, var_panel.walk_forward, var_panel.forecast, short_risk.design, short_risk.fit_var,
         short_risk.VarModel, short_risk._ols]
    consts = repr((var_panel.SYMBOLS, var_panel.FEATS, var_panel.MIN_TRAIN, var_panel.MIN_OOS, var_panel.LEVEL,
                   var_panel.EWMA_LAMBDA, sorted(short_risk.LOGGED)))
    return _fp(f, {}, consts)


def month_model_id() -> str:
    """Monthly volatility regression + the definition of its inputs/target
    (the rv / VIX lines of features.build_panel and the FeatureConfig)."""
    from . import features
    src = inspect.getsource(features.build_panel).splitlines()
    inputs = "\n".join(l for l in src if re.search(r"\brv|vix|dret", l))
    return _fp([risk_model.vol_forecast], {**asdict(risk_model.RiskConfig()), **asdict(features.FeatureConfig())}, inputs)


def _num(x, fmt: str) -> str:
    return "" if x is None or not np.isfinite(x) else format(float(x), fmt)


def forecast_rows(short_current: dict, vol_current: dict, light_level: str | None, issued_at: str,
                  now_utc: datetime, engine_version: str, challenger: dict | None = None,
                  panel: dict | None = None, cap: dict | None = None) -> list[dict]:
    rows = []
    pid = panel_model_id() if panel else None
    for sym, fc in sorted(((panel or {}).get("forecasts") or {}).items()):
        if bar_is_final("US", fc["date"], now_utc):
            rows.append({"target": f"panel_var_1d:{sym}", "origin_date": fc["date"], "issued_at": issued_at,
                         "var95": _num(fc["var95"], ".8f"), "har_var": _num(fc["har_var"], ".10e"),
                         "ewma_var": _num(fc["ewma_var"], ".10e"), "vol_ann": "", "band_lo": "", "band_hi": "",
                         "level": "", "engine_version": engine_version, "model_id": pid})
    d = short_current["date"]
    if bar_is_final("US", d, now_utc):
        sid = short_model_id(short_current["model"])
        ewma_vol = short_current.get("ewma_vol_ann")
        ewma = ewma_vol ** 2 / 252 if ewma_vol is not None else float("nan")
        base = {"origin_date": d, "issued_at": issued_at, "engine_version": engine_version, "model_id": sid,
                "vol_ann": "", "band_lo": "", "band_hi": ""}
        rows.append({**base, "target": "var_1d", "var95": _num(short_current["var95_1d_simple_ret"], ".8f"),
                     "har_var": _num(short_current["vol_1d"] ** 2, ".10e"), "ewma_var": _num(ewma, ".10e"),
                     "level": light_level or ""})
        ch = (challenger or {}).get("current") or {}
        if ch.get("var95_1d_simple_ret") is not None:
            rows.append({**base, "target": "var_1d_challenger", "model_id": challenger_model_id(short_current["model"]),
                         "var95": _num(ch["var95_1d_simple_ret"], ".8f"),
                         "har_var": _num(short_current["vol_1d"] ** 2, ".10e"), "ewma_var": _num(ewma, ".10e"),
                         "level": light_level or ""})
        rows.append({**base, "target": "vol_5d", "var95": "",
                     "har_var": _num(short_current["vol_5d"] ** 2 / 5, ".10e"), "ewma_var": _num(ewma, ".10e"),
                     "level": ""})
        if cap and cap.get("date") == d:
            rows.append({**base, "target": "exposure_cap_5d", "model_id": exposure_model_id(short_current["model"]),
                         "var95": "", "har_var": _num(short_current["vol_5d"] ** 2 / 5, ".10e"), "ewma_var": "",
                         "vol_ann": _num(cap["target_vol"], ".6f"), "band_lo": _num(cap["cap_raw"], ".6f"),
                         "band_hi": _num(cap["cap"], ".2f"), "level": cap["band"]})
    else:
        log.info("market ledger: bar %s not final yet, short-horizon forecasts not logged", d)
    me = vol_current.get("month_end")
    if me and not month_is_final(me["date"], now_utc):
        log.info("market ledger: month %s not final yet, vol_1m forecast not logged", me["date"])
        me = None
    if me:  # complete month only; the provisional mid-month forecast is never logged
        rows.append({"target": "vol_1m", "origin_date": me["date"], "issued_at": issued_at, "var95": "",
                     "har_var": "", "ewma_var": "", "vol_ann": _num(me["vol"], ".6f"),
                     "band_lo": _num(me["band90"][0], ".6f"), "band_hi": _num(me["band90"][1], ".6f"),
                     "level": "", "engine_version": engine_version, "model_id": month_model_id()})
    return rows


def month_is_final(month_end: str, now_utc: datetime) -> bool:
    """The month's last NYSE trading day has closed (the panel's partial flag
    looks at dates only and would accept an intraday last-day bar)."""
    from .features import last_trading_day_of_month
    return bar_is_final("US", str(last_trading_day_of_month(pd.Timestamp(month_end)).date()), now_utc)


def _read(path: Path, cols: list[str]) -> pd.DataFrame:
    """All text (empty fields stay ""): frozen rows are written back byte-identical."""
    if not path.exists():
        return pd.DataFrame(columns=cols)
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def evaluate(ledger: pd.DataFrame, r: pd.Series, panel: pd.DataFrame, skip: set,
             now_utc: datetime | None = None, panel_returns: dict | None = None) -> pd.DataFrame:
    """r: daily log returns of the risk asset (dated by the bar). panel: monthly
    panel with rv21 and the partial flag."""
    r = r.dropna().sort_index()
    complete = panel[~panel["partial"].astype(bool)]
    recs = []
    for _, f in ledger.iterrows():
        if (f["target"], f["origin_date"]) in skip:
            continue
        o = pd.Timestamp(f["origin_date"])
        rec = {c: f.get(c) for c in ("target", "origin_date", "var95", "har_var", "ewma_var", "vol_ann",
                                     "band_lo", "band_hi", "level", "model_id")}
        rec.update(target_end=None, status="pending", realized=None, breach=None, qlike_har=None,
                   qlike_ewma=None, ratio=None, log_error=None, in_band=None)
        series = r
        if str(f["target"]).startswith("panel_var_1d:"):
            series = (panel_returns or {}).get(str(f["target"]).split(":", 1)[1])
            if series is None:
                recs.append(rec)  # stays pending until that series is available again
                continue
        if f["target"] == "exposure_cap_5d":
            nxt = series[series.index > o]
            if len(nxt) >= 5 and (now_utc is None or bar_is_final("US", str(nxt.index[4].date()), now_utc)):
                w = nxt.iloc[:5]
                y = float((w ** 2).mean())
                ratio = float(f["band_hi"]) * sqrt(y * 252) / float(f["vol_ann"])
                rec.update(target_end=str(w.index[-1].date()), status="scored", realized=y, ratio=ratio,
                           in_band=bool(ratio <= CAP_OVERSHOOT),
                           log_error=float(np.log(ratio)) if ratio > 0 else None)
        elif f["target"] in ("var_1d", "var_1d_challenger", "vol_5d") or str(f["target"]).startswith("panel_var_1d:"):
            h = 5 if f["target"] == "vol_5d" else 1
            nxt = series[series.index > o]
            if len(nxt) >= h and (now_utc is None or bar_is_final("US", str(nxt.index[h - 1].date()), now_utc)):
                w = nxt.iloc[:h]
                y = float((w ** 2).mean())
                hv, ev = float(f["har_var"]), float(f["ewma_var"])
                rec.update(target_end=str(w.index[-1].date()), status="scored", realized=y,
                           qlike_har=float(qlike(np.array([y]), np.array([hv]))[0]),
                           qlike_ewma=float(qlike(np.array([y]), np.array([ev]))[0]), ratio=y / hv)
                if h == 1:
                    v = pd.to_numeric(f["var95"], errors="coerce")
                    if not np.isfinite(v):
                        rec["status"] = "invalid"  # no VaR value: never counted as "no breach"
                    else:
                        rec["breach"] = bool(np.expm1(float(w.iloc[0])) < -float(v))
        else:  # vol_1m: realized rv21 of the next COMPLETE month
            nxt = complete[complete.index > o]
            if len(nxt) and pd.notna(nxt["rv21"].iloc[0]) and (
                    now_utc is None or month_is_final(str(nxt.index[0].date()), now_utc)):
                y = float(nxt["rv21"].iloc[0])
                fc, lo, hi = float(f["vol_ann"]), float(f["band_lo"]), float(f["band_hi"])
                rec.update(target_end=str(nxt.index[0].date()), status="scored", realized=y,
                           log_error=float(np.log(y / fc)), ratio=y / fc, in_band=bool(lo <= y <= hi))
        recs.append(rec)
    return pd.DataFrame(recs, columns=OUTCOME_COLUMNS)


def _summ_var(s: pd.DataFrame, cfg: MarketReviewConfig) -> dict:
    s = s.sort_values("origin_date")
    br = s["breach"].map(lambda v: v in (True, "True", 1, "1")).to_numpy()
    out = {"n": int(len(s)), "breaches": int(br.sum()), "breach_rate": float(br.mean()) if len(br) else None,
           "kupiec_p": None, "christoffersen_p": None, "verdict": "insufficient",
           "first_date": s["origin_date"].min() if len(s) else None}
    if len(s):
        out["var_ratio"] = float(s["ratio"].astype(float).mean())
        if len(s) >= 30:
            out["dm_t_vs_ewma"] = diebold_mariano(s["qlike_ewma"].astype(float).to_numpy(),
                                                  s["qlike_har"].astype(float).to_numpy(), 5)
        tail = br[-cfg.rolling_days:]
        out["rolling"] = {"n": int(len(tail)), "breaches": int(tail.sum()), "breach_rate": float(tail.mean())}
        lv = {}
        for k, g in s.groupby("level"):
            if k and isinstance(k, str):
                lv[k] = {"n": int(len(g)), "realized_vol_ann": float(sqrt(g["realized"].astype(float).mean() * 252)),
                         "forecast_vol_ann": float(sqrt(g["har_var"].astype(float).mean() * 252))}
        out["by_light"] = lv
    out["interim"] = sequential.single_series(br)  # registered early-warning looks (section 20)
    if len(s) >= cfg.min_days_var:
        k, c = kupiec(br, cfg.var_level), christoffersen(br)
        out.update(kupiec_p=k["p_value"], christoffersen_p=c["p_value"])
        out["verdict"] = ("consistent" if k["p_value"] >= 0.05 and c["p_value"] >= 0.05
                          else "coverage_rejected" if k["p_value"] < 0.05 else "breaches_cluster")
    return out


def _summ_5d(s: pd.DataFrame) -> dict:
    out = {"n": int(len(s))}
    if len(s):
        out["var_ratio"] = float(s["ratio"].astype(float).mean())
        if len(s) >= 30:
            out["dm_t_vs_ewma"] = diebold_mariano(s["qlike_ewma"].astype(float).to_numpy(),
                                                  s["qlike_har"].astype(float).to_numpy(), 5)
    return out


def _summ_cap(s: pd.DataFrame) -> dict:
    """Descriptive only (overlapping 5-day windows): did the cap keep risk near target?"""
    out = {"n": int(len(s))}
    if len(s):
        rt = s["ratio"].astype(float)
        out.update(median_ratio=float(rt.median()), share_above_overshoot=float((rt > CAP_OVERSHOOT).mean()),
                   overshoot=CAP_OVERSHOOT)
    return out


def _binom_two_sided(k: int, n: int, p: float) -> float:
    from math import comb
    pmf = [comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(n + 1)]
    return float(min(1.0, sum(q for q in pmf if q <= pmf[k] * (1 + 1e-12))))


def _summ_1m(s: pd.DataFrame, cfg: MarketReviewConfig) -> dict:
    out = {"n": int(len(s)), "verdict": "insufficient"}
    if len(s):
        e = s["log_error"].astype(float)
        inb = s["in_band"].map(lambda v: v in (True, "True", 1, "1"))
        out.update(mean_log_error=float(e.mean()), mae_log=float(e.abs().mean()), band_coverage=float(inb.mean()))
        if len(s) >= cfg.min_months_vol:
            # Exact two-sided binomial test of coverage = 0.90 (the fixed 0.80-0.97
            # range used until 2026-11-23 flagged a perfect 24/24 record).
            k, n = int(inb.sum()), int(len(s))
            out["band_coverage_p"] = _binom_two_sided(k, n, 0.90)
            out["verdict"] = "consistent" if out["band_coverage_p"] >= 0.05 else "band_miscalibrated"
    return out


def update(out_dir: Path, raw, panel: pd.DataFrame, short_current: dict, vol_current: dict,
           light_level: str | None, issued_at: str, now_utc: datetime, engine_version: str,
           cfg: MarketReviewConfig | None = None, challenger: dict | None = None,
           var_panel_fc: dict | None = None, panel_returns: dict | None = None, cap: dict | None = None) -> dict:
    cfg = cfg or MarketReviewConfig()
    out_dir = Path(out_dir)
    lp = out_dir / "forecasts" / "market_ledger.csv"
    op = out_dir / "forecasts" / "market_outcomes.csv"
    added = append_ledger(lp, forecast_rows(short_current, vol_current, light_level, issued_at, now_utc, engine_version,
                                            challenger, var_panel_fc, cap),
                          COLUMNS, ("target", "origin_date"))
    led = _read(lp, COLUMNS)
    old = _read(op, OUTCOME_COLUMNS)
    final = old[old["status"].isin(FINAL_STATUSES)]
    skip = set(zip(final["target"], final["origin_date"]))
    r = short_risk.daily_frame(raw, short_risk.ShortRiskConfig())["r"]
    fresh = evaluate(led, r, panel, skip, now_utc, panel_returns)
    outcomes = pd.concat([final, fresh], ignore_index=True) if len(final) else fresh
    outcomes = outcomes.sort_values(["origin_date", "target"], kind="stable").reset_index(drop=True)
    _atomic_write(op, outcomes.to_csv(index=False, lineterminator="\n"))

    current = {"var_1d": short_model_id(short_current["model"]), "vol_5d": short_model_id(short_current["model"]),
               "vol_1m": month_model_id(), "var_1d_challenger": challenger_model_id(short_current["model"]),
               "exposure_cap_5d": exposure_model_id(short_current["model"])}
    sc = outcomes[outcomes["status"] == "scored"]
    # Live VaR breaches scored in THIS run (alerts, section 21).
    nb = fresh[(fresh["target"] == "var_1d") & (fresh["status"] == "scored") & (fresh["model_id"] == current["var_1d"])
               & fresh["breach"].map(lambda v: v is True)]
    new_breaches = [{"origin_date": x["origin_date"], "target_end": x["target_end"],
                     "var95": float(x["var95"]), "ret": float(np.expm1(r.loc[pd.Timestamp(x["target_end"])]))}
                    for _, x in nb.iterrows()]
    review = {"as_of": issued_at, "settings": asdict(cfg), "current_models": current, "targets": {},
              "last_run": {"forecasts_added": added, "new_var_breaches": new_breaches}}
    for t, mid in current.items():
        lt = led[led["target"] == t]
        st = sc[(sc["target"] == t) & (sc["model_id"] == mid)]
        summ = (_summ_var(st, cfg) if t in ("var_1d", "var_1d_challenger") else _summ_5d(st) if t == "vol_5d"
                else _summ_cap(st) if t == "exposure_cap_5d" else _summ_1m(st, cfg))
        review["targets"][t] = {**summ, "logged": int((lt["model_id"] == mid).sum()),
                                "logged_since": lt.loc[lt["model_id"] == mid, "origin_date"].min() if len(lt) else None,
                                "other_models": {k: int(v) for k, v in lt.loc[lt["model_id"] != mid, "model_id"].value_counts().items()},
                                "pending": int(((outcomes["target"] == t) & (outcomes["status"] == "pending")).sum())}
    # Multi-market panel of the VaR method (section 20): pooled interim looks.
    pid = panel_model_id()
    ps = sc[sc["target"].astype(str).str.startswith("panel_var_1d:") & (sc["model_id"] == pid)].copy()
    pl = led[led["target"].astype(str).str.startswith("panel_var_1d:")]
    if len(ps):
        ps["b"] = ps["breach"].map(lambda v: v in (True, "True", 1, "1")).astype(float)
    per = {}
    for t, g in ps.groupby("target") if len(ps) else []:
        per[t.split(":", 1)[1]] = {"n": int(len(g)), "breaches": int(g["b"].sum()), "rate": float(g["b"].mean())}
    review["panel"] = {"model_id": pid, "symbols": list(var_panel.SYMBOLS), "per_symbol": per,
                       "logged": int((pl["model_id"] == pid).sum()), "n": int(len(ps)),
                       "n_dates": int(ps["origin_date"].nunique()) if len(ps) else 0,
                       "rate": float(ps["b"].mean()) if len(ps) else None,
                       "interim": sequential.pooled(ps["b"].to_numpy(), ps["origin_date"].to_numpy()) if len(ps)
                       else sequential.pooled(np.array([]), np.array([]))}
    # Registered challenger vs incumbent, on days scored for both (methodology section 18).
    a = sc[(sc["target"] == "var_1d") & (sc["model_id"] == current["var_1d"])]
    b = sc[(sc["target"] == "var_1d_challenger") & (sc["model_id"] == current["var_1d_challenger"])]
    common = sorted(set(a["origin_date"]) & set(b["origin_date"]))
    inc = _summ_var(a[a["origin_date"].isin(common)], cfg)
    chs = _summ_var(b[b["origin_date"].isin(common)], cfg)
    review["challenger_comparison"] = {"common_days": len(common), "incumbent": inc, "challenger": chs,
                                       "decision": var_challenger.live_decision(chs, inc),
                                       "rule": "after >= 250 common live days: recommend switching only if the incumbent "
                                               "fails Kupiec or Christoffersen and the challenger passes both"}
    from .export import clean
    _atomic_write(out_dir / "forecast_review_market.json", json.dumps(clean(review), indent=1, allow_nan=False) + "\n")
    log.info("market ledger: +%d forecasts (total %d); scored %d", added, len(led), len(sc))
    return review
