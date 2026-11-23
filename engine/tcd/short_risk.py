"""Short-horizon (1-day / 5-day) volatility and 95% VaR on daily data.

Models (all forecast the average daily variance over t+1..t+h):
    EWMA      RiskMetrics, lambda = 0.94 (industry baseline, no fitting)
    HAR       Corsi (2009): RV_d, RV_w (5d), RV_m (22d) -> OLS on levels
    HAR+VIX   + implied daily variance (VIX/100)^2 / 252
    HAR+VIX+EPU  + log 30-day mean of the daily Economic Policy Uncertainty
                 index, lagged one day (EPU is published the next day)

Realized variance proxy: squared daily close-to-close returns (no intraday
data). Walk-forward: refit each January on days whose target window ended
by December of the previous year. Variance forecasts are scored with QLIKE
(robust to noisy proxies, Patton 2011) and Diebold-Mariano tests with
Newey-West variance. 1-day 95% VaR uses filtered historical simulation
(training quantile of standardized returns) and is backtested with Kupiec
(coverage) and Christoffersen (independence) tests.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import erfc, exp, log, sqrt

import numpy as np
import pandas as pd

from .fetch import RawData

MODELS = ("ewma", "har", "har_vix", "har_vix_epu")
MODEL_LABELS = {"ewma": "EWMA (RiskMetrics 0.94)", "har": "HAR", "har_vix": "HAR + VIX", "har_vix_epu": "HAR + VIX + EPU"}
FEATURES = {"har": ["rv_d", "rv_w", "rv_m"], "har_vix": ["rv_d", "rv_w", "rv_m", "vix_var"],
            "har_vix_epu": ["rv_d", "rv_w", "rv_m", "vix_var", "epu"]}


@dataclass(frozen=True)
class ShortRiskConfig:
    horizons: tuple[int, ...] = (1, 5)
    oos_start_year: int = 2000
    train_start: str = "1990-02-01"
    ewma_lambda: float = 0.94
    var_level: float = 0.05
    epu_window: int = 30
    min_train_days: int = 1000
    var_floor: float = 1e-8
    # "log": log-HAR (forecasts always positive; smearing bias correction) - primary.
    # "level": classic Corsi OLS on variance levels - reported for robustness.
    spec: str = "log"
    log_floor: float = 1e-8  # floor for squared returns before taking logs
    # FHS quantile source. "oos": standardized returns of earlier OUT-OF-SAMPLE
    # forecasts (expanding window; fixes the under-coverage of in-sample
    # residuals, whose fitted variance is optimistic). "insample": the
    # original rule, still reported for comparison.
    var_quantile: str = "oos"
    min_oos_resid: int = 500  # earlier OOS residuals needed before a quantile is set


# ----------------------------------------------------------------- data
def daily_frame(raw: RawData, cfg: ShortRiskConfig) -> pd.DataFrame:
    xlk = raw.xlk["adjclose"]
    ndx = raw.ndx["close"]
    r_xlk = np.log(xlk).diff()
    r_ndx = np.log(ndx).diff()
    first_xlk = r_xlk.dropna().index.min()
    r = pd.concat([r_ndx[r_ndx.index < first_xlk], r_xlk[r_xlk.index >= first_xlk]]).dropna()
    r = r[~r.index.duplicated()].sort_index()
    df = pd.DataFrame({"r": r})
    r2 = df["r"] ** 2
    df["rv_d"] = r2
    df["rv_w"] = r2.rolling(5).mean()
    df["rv_m"] = r2.rolling(22).mean()
    vix = raw.vix.reindex(df.index, method="ffill")
    df["vix_var"] = (vix / 100.0) ** 2 / 252.0
    epu = raw.fred.get("epu")
    if epu is not None and len(epu):
        epu_avg = epu.rolling(cfg.epu_window, min_periods=cfg.epu_window // 2).mean()
        # Value for calendar day d is published on d+1: at the close of t use data dated <= t-1.
        epu_avg = epu_avg.copy()
        epu_avg.index = epu_avg.index + pd.Timedelta(days=1)
        df["epu"] = np.log(epu_avg.reindex(df.index, method="ffill"))
    else:
        df["epu"] = np.nan
    # EWMA variance (uses information through t).
    lam = cfg.ewma_lambda
    ew = np.empty(len(df))
    ew[0] = r2.iloc[:22].mean()
    rr = r2.to_numpy()
    for i in range(1, len(df)):
        ew[i] = lam * ew[i - 1] + (1 - lam) * rr[i]
    df["ewma"] = ew
    for h in cfg.horizons:
        df[f"y{h}"] = sum(r2.shift(-k) for k in range(1, h + 1)) / h
    df["r_next"] = df["r"].shift(-1)
    return df.loc[pd.Timestamp(cfg.train_start):]


# ------------------------------------------------------------- statistics
def qlike(y: np.ndarray, f: np.ndarray) -> np.ndarray:
    """QLIKE loss in the form log f + y/f (defined for y == 0). It differs from
    y/f - log(y/f) - 1 only by a term that does not depend on f, so model
    rankings and Diebold-Mariano tests are the same; levels are not comparable
    with papers that report the other form."""
    return np.log(f) + y / f


def diebold_mariano(loss_a: np.ndarray, loss_b: np.ndarray, lag: int) -> float:
    """t-stat of mean(loss_a - loss_b) with Newey-West variance. Positive => b is better."""
    d = loss_a - loss_b
    d = d[np.isfinite(d)]
    n = len(d)
    if n < 30:
        return float("nan")
    u = d - d.mean()
    s = np.dot(u, u) / n
    for L in range(1, lag + 1):
        s += 2 * (1 - L / (lag + 1)) * np.dot(u[L:], u[:-L]) / n
    return float(d.mean() / sqrt(s / n)) if s > 0 else float("nan")


def kupiec(breaches: np.ndarray, p: float) -> dict:
    n, x = len(breaches), int(breaches.sum())
    if n == 0:
        return {"n": 0}
    pi = x / n
    ll0 = (n - x) * log(1 - p) + x * log(p)
    ll1 = ((n - x) * log(1 - pi) if pi < 1 else 0.0) + (x * log(pi) if pi > 0 else 0.0)
    lr = -2 * (ll0 - ll1)
    return {"n": n, "breaches": x, "rate": pi, "lr": lr, "p_value": erfc(sqrt(max(lr, 0) / 2))}


def christoffersen(breaches: np.ndarray) -> dict:
    b = breaches.astype(int)
    a, c = b[:-1], b[1:]
    n00, n01 = int(((a == 0) & (c == 0)).sum()), int(((a == 0) & (c == 1)).sum())
    n10, n11 = int(((a == 1) & (c == 0)).sum()), int(((a == 1) & (c == 1)).sum())
    p01 = n01 / (n00 + n01) if n00 + n01 else 0.0
    p11 = n11 / (n10 + n11) if n10 + n11 else 0.0
    p = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)

    def ll(k0, k1, q):
        return (k0 * log(1 - q) if q < 1 and k0 else 0.0) + (k1 * log(q) if q > 0 and k1 else 0.0)

    lr = -2 * (ll(n00 + n10, n01 + n11, p) - ll(n00, n01, p01) - ll(n10, n11, p11))
    return {"p01": p01, "p11": p11, "lr": lr, "p_value": erfc(sqrt(max(lr, 0) / 2))}


# ------------------------------------------------------------ walk-forward
def _ols(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    Z = np.column_stack([np.ones(len(X)), X])
    beta, *_ = np.linalg.lstsq(Z, y, rcond=None)
    return beta


LOGGED = {"rv_d", "rv_w", "rv_m", "vix_var"}  # epu is already a log level


@dataclass
class VarModel:
    feats: list[str]
    spec: str
    beta: np.ndarray
    smear: float = 1.0  # Duan smearing factor for the log spec

    def predict(self, df_or_X, floor: float) -> np.ndarray:
        X = df_or_X
        if self.spec == "log":
            return np.maximum(np.exp(self.beta[0] + X @ self.beta[1:]) * self.smear, floor)
        return np.maximum(self.beta[0] + X @ self.beta[1:], floor)


def design(df: pd.DataFrame, feats: list[str], spec: str, log_floor: float) -> np.ndarray:
    cols = []
    for f in feats:
        v = df[f].to_numpy(float)
        cols.append(np.log(np.maximum(v, log_floor)) if (spec == "log" and f in LOGGED) else v)
    return np.column_stack(cols)


def fit_var(X: np.ndarray, y: np.ndarray, feats: list[str], spec: str, log_floor: float) -> VarModel:
    if spec == "log":
        ly = np.log(np.maximum(y, log_floor))
        beta = _ols(X, ly)
        resid = ly - (beta[0] + X @ beta[1:])
        return VarModel(feats, spec, beta, float(np.mean(np.exp(resid))))
    return VarModel(feats, spec, _ols(X, y))


def oos_quantile(out: pd.DataFrame, m: str, r_next: np.ndarray, known: np.ndarray, cfg: ShortRiskConfig) -> float:
    col = f"{m}_1"
    if col not in out:
        return float("nan")
    f = out[col].to_numpy(float)
    ok = known & np.isfinite(f) & np.isfinite(r_next)
    if ok.sum() < cfg.min_oos_resid:
        return float("nan")
    return float(np.nanquantile(r_next[ok] / np.sqrt(f[ok]), cfg.var_level))


def walk_forward(df: pd.DataFrame, cfg: ShortRiskConfig) -> tuple[pd.DataFrame, dict]:
    """OOS variance forecasts for every model/horizon + FHS 1-day VaR quantiles."""
    idx = df.index
    out = pd.DataFrame(index=idx)
    coefs: dict[str, list] = {m: [] for m in FEATURES}
    last_year = int(idx[-1].year)
    for h in cfg.horizons:
        out[f"ewma_{h}"] = df["ewma"]  # EWMA h-step forecast = current EWMA variance
    r_next = df["r_next"].to_numpy(float)
    # Forecasts start in the first year with enough training data (burn-in for
    # the OOS-residual quantile); evaluation still starts at oos_start_year.
    for Y in range(int(idx[0].year) + 1, last_year + 1):
        train_end = pd.Timestamp(f"{Y - 1}-12-31")
        test = idx.year == Y
        if not test.any():
            continue
        for m, feats in FEATURES.items():
            Xall = design(df, feats, cfg.spec, cfg.log_floor)
            ok = ~np.isnan(Xall).any(axis=1)
            for h in cfg.horizons:
                y = df[f"y{h}"].to_numpy(float)
                # target window t+1..t+h must end by train_end
                # Target window t+1..t+h must end by train_end, using the actual
                # trading-day index (BDay ignored exchange holidays and let a
                # window around Christmas reach into the test year).
                end_pos = np.minimum(np.arange(len(idx)) + h, len(idx) - 1)
                known = (idx[end_pos] <= train_end) & (np.arange(len(idx)) + h < len(idx))
                tr = ok & known & ~np.isnan(y)
                if tr.sum() < cfg.min_train_days:
                    continue
                model = fit_var(Xall[tr], y[tr], feats, cfg.spec, cfg.log_floor)
                te = test & ok
                out.loc[te, f"{m}_{h}"] = model.predict(Xall[te], cfg.var_floor)
                if h == 1:
                    coefs[m].append({"year": Y, "coef": dict(zip(["const"] + feats, map(float, model.beta)))})
                    # In-sample FHS quantile (original rule, kept for comparison).
                    fit = model.predict(Xall[tr], cfg.var_floor)
                    z = r_next[tr] / np.sqrt(fit)
                    out.loc[test, f"qin_{m}"] = float(np.nanquantile(z, cfg.var_level))
                    # OOS FHS quantile: earlier out-of-sample forecasts whose outcome
                    # was known by train_end.
                    out.loc[test, f"qoos_{m}"] = oos_quantile(out, m, r_next, known, cfg)
                    out.loc[test, f"q_{m}"] = out.loc[test, f"q{'oos' if cfg.var_quantile == 'oos' else 'in'}_{m}"]
        # EWMA quantile: normal (RiskMetrics convention).
        out.loc[test, "q_ewma"] = -1.6448536269514722
    return out, coefs


def evaluate(df: pd.DataFrame, fc: pd.DataFrame, cfg: ShortRiskConfig) -> dict:
    oos = fc.index.year >= cfg.oos_start_year
    res = {"variance": [], "var95": [], "dm": []}
    for h in cfg.horizons:
        y = df[f"y{h}"].to_numpy(float)
        cols = {m: fc.get(f"{m}_{h}") for m in MODELS}
        common = oos & ~np.isnan(y)
        for m, s in cols.items():
            if s is None:
                continue
            common &= s.notna().to_numpy()
        losses = {}
        for m, s in cols.items():
            f = s.to_numpy(float)[common]
            yy = y[common]
            losses[m] = qlike(yy, f)
            mse = float(np.mean((yy - f) ** 2))
            # Mincer-Zarnowitz R^2 of the realized proxy on the forecast (levels).
            # The former "r2_log" compared log forecasts with the log of single
            # squared returns (log-chi2 bias, zero days at log 1e-12): not informative.
            mz_r2 = float(np.corrcoef(f, yy)[0, 1] ** 2)
            res["variance"].append({"horizon": h, "model": m, "label": MODEL_LABELS[m], "n": int(common.sum()),
                                    "qlike": float(losses[m].mean()), "mse_x1e8": mse * 1e8,
                                    "corr_vol": float(np.corrcoef(np.sqrt(f), np.sqrt(yy))[0, 1]),
                                    "mz_r2": mz_r2})
        for a, b in (("ewma", "har"), ("har", "har_vix"), ("ewma", "har_vix"), ("har_vix", "har_vix_epu")):
            res["dm"].append({"horizon": h, "baseline": a, "challenger": b,
                              "qlike_improvement": float(losses[a].mean() - losses[b].mean()),
                              "dm_t": diebold_mariano(losses[a], losses[b], max(h, 5))})
    # 1-day 95% VaR backtest. All variants are scored on the same days (where
    # every quantile exists) so that their breach rates are comparable.
    r_next = df["r_next"].to_numpy(float)
    res["var95_quantile"] = cfg.var_quantile
    res["var95_by_quantile"] = {"oos": [], "insample": []}
    for m in MODELS:
        f = fc.get(f"{m}_1")
        if f is None:
            continue
        cols = {"oos": fc.get(f"qoos_{m}", fc.get(f"q_{m}")), "insample": fc.get(f"qin_{m}", fc.get(f"q_{m}"))}
        ok = oos & f.notna().to_numpy() & ~np.isnan(r_next)
        for q in cols.values():
            ok &= q.notna().to_numpy()
        for name, q in cols.items():
            var_ret = q.to_numpy(float)[ok] * np.sqrt(f.to_numpy(float)[ok])  # negative return threshold
            br = r_next[ok] < var_ret
            row = {"model": m, "label": MODEL_LABELS[m], **kupiec(br, cfg.var_level),
                   "christoffersen": christoffersen(br), "avg_var": float(-np.mean(var_ret)),
                   "start": str(fc.index[ok][0].date())}
            res["var95_by_quantile"][name].append(row)
    res["var95"] = res["var95_by_quantile"]["oos" if cfg.var_quantile == "oos" else "insample"]
    return res


def epu_verdict(dm_rows: list[dict]) -> str:
    rows = [d for d in dm_rows if d["baseline"] == "har_vix" and d["challenger"] == "har_vix_epu"]
    if not rows:
        return "not evaluated"
    good = [d for d in rows if d["qlike_improvement"] > 0 and d["dm_t"] >= 2]
    bad = [d for d in rows if d["dm_t"] <= -2]
    if len(good) == len(rows):
        return "keep: EPU significantly improves QLIKE at every horizon"
    if bad:
        return "drop: EPU significantly worsens forecasts"
    return "drop: no significant improvement from EPU (pre-set rule: improvement with DM t >= 2 at every horizon)"


def current(df: pd.DataFrame, cfg: ShortRiskConfig, model: str, fc: pd.DataFrame | None = None) -> dict:
    """Fit on all known targets; forecast from the latest close. The VaR
    quantile follows cfg.var_quantile (OOS: all walk-forward residuals so far)."""
    feats = FEATURES[model]
    X = design(df, feats, cfg.spec, cfg.log_floor)
    ok = ~np.isnan(X).any(axis=1)
    out = {"date": str(df.index[-1].date()), "model": model, "label": MODEL_LABELS[model], "spec": cfg.spec}
    for h in cfg.horizons:
        y = df[f"y{h}"].to_numpy(float)
        tr = ok & ~np.isnan(y)
        vm = fit_var(X[tr], y[tr], feats, cfg.spec, cfg.log_floor)
        fv = float(vm.predict(X[-1:], cfg.var_floor)[0])
        out[f"vol_{h}d_ann"] = sqrt(fv * 252)
        out[f"vol_{h}d"] = sqrt(fv * h)  # h-day horizon vol (not annualized)
        if h == 1:
            fit = vm.predict(X[tr], cfg.var_floor)
            z = df["r_next"].to_numpy(float)[tr] / np.sqrt(fit)
            q_in = float(np.nanquantile(z, cfg.var_level))
            q = q_in
            if cfg.var_quantile == "oos" and fc is not None:
                known = ~np.isnan(df["r_next"].to_numpy(float))
                q_oos = oos_quantile(fc, model, df["r_next"].to_numpy(float), known, cfg)
                if np.isfinite(q_oos):
                    q = q_oos
            out["var_quantile"] = {"used": q, "insample": q_in, "source": cfg.var_quantile}
            out["var95_1d_insample_simple_ret"] = float(1 - exp(q_in * sqrt(fv)))
            out["var95_1d"] = float(-(q * sqrt(fv)))  # positive = loss
            out["var95_1d_simple_ret"] = float(1 - exp(q * sqrt(fv)))
    out["ewma_vol_ann"] = sqrt(float(df["ewma"].iloc[-1]) * 252)
    # Where tomorrow's forecast sits in the history of 22-day realized vol
    # (all days up to the latest close; point-in-time).
    hist = np.sqrt(df["rv_m"].dropna() * 252)
    out["vol_hist_percentile"] = float((hist <= out["vol_1d_ann"]).mean())
    out["vol_hist_median"] = float(hist.median())
    out["vol_hist_start"] = str(hist.index[0].date())
    out["vol_hist_days"] = int(len(hist))
    return out


def run_short_risk(raw: RawData, cfg: ShortRiskConfig | None = None) -> dict:
    cfg = cfg or ShortRiskConfig()
    df = daily_frame(raw, cfg)
    fc, coefs = walk_forward(df, cfg)
    ev = evaluate(df, fc, cfg)
    alt = replace(cfg, spec="level" if cfg.spec == "log" else "log")
    fc_alt, _ = walk_forward(df, alt)
    ev_alt = evaluate(df, fc_alt, alt)
    v_primary, v_alt = epu_verdict(ev["dm"]), epu_verdict(ev_alt["dm"])
    verdict = v_primary if v_primary.startswith("keep") and v_alt.startswith("keep") else (
        v_primary if not v_primary.startswith("keep") else "drop: EPU helps under one specification only (" + alt.spec + ": " + v_alt + ")")
    live_model = "har_vix_epu" if verdict.startswith("keep") else "har_vix"
    oos = fc.index.year >= cfg.oos_start_year
    tail = fc.loc[oos].iloc[-756:]  # ~3 years for the chart
    rn = df["r_next"].reindex(tail.index)
    q = tail[f"q_{live_model}"]
    var_line = -(q * np.sqrt(tail[f"{live_model}_1"]))
    return {
        "settings": {"models": MODEL_LABELS, "horizons": list(cfg.horizons), "oos_start_year": cfg.oos_start_year,
                     "var": "1-day 95%, filtered historical simulation (EWMA: normal); quantile of standardized returns of earlier out-of-sample forecasts (expanding window, >= 500 days)" if cfg.var_quantile == "oos" else "1-day 95%, filtered historical simulation (EWMA: normal); in-sample quantile",
                     "proxy": "squared daily close-to-close returns of the risk asset",
                     "epu": f"FRED USEPUINDXD, log {cfg.epu_window}-day mean, lagged one day",
                     "epu_rule": "keep EPU only if QLIKE improves with Diebold-Mariano t >= 2 at every horizon, under both the log (primary) and level specifications"},
        "evaluation": ev,
        "robustness": {"spec": alt.spec, "evaluation": ev_alt, "epu_verdict": v_alt},
        "spec": cfg.spec,
        "epu_verdict": verdict,
        "live_model": live_model,
        "coefficients": {m: c[-5:] for m, c in coefs.items()},
        "current": current(df, cfg, live_model, fc),
        "chart": {"dates": [str(d.date()) for d in tail.index],
                  "next_day_return": [None if pd.isna(v) else round(float(v), 5) for v in rn],
                  "var95": [None if pd.isna(v) else round(float(v), 5) for v in var_line]},
    }
