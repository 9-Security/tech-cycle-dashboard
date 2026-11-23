"""Calibrated probability of a large drawdown (walk-forward logistic model).

Target  y_t = 1 if the risk asset's max drawdown over months t+1..t+h
        (month-end closes, starting from 1.0 at t) is worse than `cut`.
Inputs  features known at month-end t.

Label-leakage rule: y_t is only known at t+h. The model used for calendar
year Y is fitted on rows t with t + h <= December of Y-1, so no training
label overlaps the period being predicted.

Evaluation is out-of-sample from `oos_start_year`: Brier score, Brier skill
score vs climatology (expanding base rate), log loss, AUC and a reliability
table. Forward windows overlap, so uncertainty uses a 12-month moving-block
bootstrap.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .signal_study import forward_max_drawdown

FEATURES = {
    "log_rv63": "log 63d realized vol",
    "log_vix": "log VIX (monthly mean)",
    "earn_score": "Earnings momentum score",
    "px_z": "Price extension z (momentum)",
}
VOL_ONLY = ("log_rv63", "log_vix")


@dataclass(frozen=True)
class RiskConfig:
    targets: tuple[tuple[int, float], ...] = ((12, -0.20), (6, -0.10))  # (horizon months, drawdown cut)
    oos_start_year: int = 2000
    l2: float = 1.0
    min_train: int = 60
    min_positives: int = 5
    bins: tuple[float, ...] = (0.0, 0.05, 0.10, 0.20, 0.30, 0.50, 1.0)
    boot_reps: int = 500
    current_boot_reps: int = 200
    seed: int = 7


# ------------------------------------------------------------------- model
def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -35, 35)))


@dataclass
class Logit:
    mean: np.ndarray
    sd: np.ndarray
    coef: np.ndarray  # [intercept, betas on standardized features]
    features: tuple[str, ...] = field(default_factory=tuple)

    def predict(self, X: np.ndarray) -> np.ndarray:
        Z = (X - self.mean) / self.sd
        return _sigmoid(self.coef[0] + Z @ self.coef[1:])

    def contributions(self, x: np.ndarray) -> dict[str, float]:
        z = (x - self.mean) / self.sd
        return {f: float(b * v) for f, b, v in zip(self.features, self.coef[1:], z)}


def fit_logit(X: np.ndarray, y: np.ndarray, l2: float = 1.0, features: tuple[str, ...] = (), iters: int = 100) -> Logit:
    """L2-penalised logistic regression via Newton-Raphson (intercept unpenalised)."""
    mean = X.mean(axis=0)
    sd = X.std(axis=0, ddof=0)
    sd = np.where(sd > 0, sd, 1.0)
    Z = np.column_stack([np.ones(len(X)), (X - mean) / sd])
    w = np.zeros(Z.shape[1])
    base = np.clip(y.mean(), 1e-4, 1 - 1e-4)
    w[0] = np.log(base / (1 - base))
    R = np.eye(Z.shape[1]) * l2
    R[0, 0] = 0.0
    for _ in range(iters):
        p = _sigmoid(Z @ w)
        g = Z.T @ (p - y) + R @ w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + R + 1e-9 * np.eye(len(w))
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-8:
            break
    return Logit(mean=mean, sd=sd, coef=w, features=features)


# ----------------------------------------------------------------- metrics
def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def auc(p: np.ndarray, y: np.ndarray) -> float:
    pos, neg = p[y == 1], p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    ranks = pd.Series(np.concatenate([pos, neg])).rank().to_numpy()
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def reliability(p: np.ndarray, y: np.ndarray, bins: tuple[float, ...]) -> list[dict]:
    rows = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & ((p < hi) if hi < 1 else (p <= hi))
        rows.append({"bin": f"{lo:.0%}-{hi:.0%}", "n": int(m.sum()),
                     "mean_pred": float(p[m].mean()) if m.any() else None,
                     "observed": float(y[m].mean()) if m.any() else None})
    return rows


def block_bootstrap_bss(p: np.ndarray, p_ref: np.ndarray, y: np.ndarray, block: int = 12,
                        reps: int = 500, seed: int = 0) -> tuple[float, float]:
    n = len(y)
    rng = np.random.default_rng(seed)
    k = int(np.ceil(n / block))
    out = np.empty(reps)
    for r in range(reps):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.integers(0, n - block + 1, k)])[:n]
        bref = brier(p_ref[idx], y[idx])
        out[r] = 1 - brier(p[idx], y[idx]) / bref if bref > 0 else np.nan
    lo, hi = np.nanpercentile(out, [5, 95])
    return float(lo), float(hi)


# ----------------------------------------------------------------- dataset
def feature_frame(panel: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({
        "log_rv63": np.log(panel["rv63"]),
        "log_vix": np.log(panel["vix"]),
        "earn_score": panel["earn_score"],
        "px_z": panel["val_z_proxy"],
    }, index=panel.index)


def labels(risk_ret: pd.Series, horizon: int, cut: float) -> pd.Series:
    dd = forward_max_drawdown(risk_ret, horizon)
    return (dd < cut).astype(float).where(dd.notna())


# --------------------------------------------------------------- walk-forward
def walk_forward(F: pd.DataFrame, y: pd.Series, features: tuple[str, ...], horizon: int,
                 cfg: RiskConfig, last_year: int) -> tuple[pd.DataFrame, list[dict]]:
    """OOS predictions for every month from oos_start_year to the end of F."""
    X_all = F[list(features)].to_numpy(float)
    feat_ok = ~np.isnan(X_all).any(axis=1)
    idx = F.index
    preds = pd.DataFrame(index=idx, columns=["p_model", "p_clim"], dtype=float)
    folds = []
    for Y in range(cfg.oos_start_year, last_year + 1):
        train_end = pd.Timestamp(f"{Y - 1}-12-31")
        label_known = idx + pd.offsets.MonthEnd(horizon) <= train_end
        tr = feat_ok & label_known & y.notna().to_numpy()
        test = (idx.year == Y) & feat_ok
        if not test.any():
            continue
        yt = y.to_numpy(float)[tr]
        clim = float(yt.mean()) if len(yt) else np.nan
        preds.loc[test, "p_clim"] = clim
        fold = {"year": Y, "n_train": int(tr.sum()), "positives": int(yt.sum()), "base_rate": clim}
        if tr.sum() >= cfg.min_train and yt.sum() >= cfg.min_positives and (len(yt) - yt.sum()) >= cfg.min_positives:
            m = fit_logit(X_all[tr], yt, cfg.l2, features)
            preds.loc[test, "p_model"] = m.predict(X_all[test])
            fold["coef"] = {f: float(b) for f, b in zip(features, m.coef[1:])}
            fold["fallback"] = False
        else:
            preds.loc[test, "p_model"] = clim
            fold["coef"] = None
            fold["fallback"] = True
        folds.append(fold)
    preds["y"] = y
    return preds, folds


def evaluate(preds: pd.DataFrame, cfg: RiskConfig) -> dict:
    d = preds.dropna(subset=["p_model", "p_clim", "y"])
    p, pc, yv = d["p_model"].to_numpy(float), d["p_clim"].to_numpy(float), d["y"].to_numpy(float)
    b, bc = brier(p, yv), brier(pc, yv)
    lo, hi = block_bootstrap_bss(p, pc, yv, reps=cfg.boot_reps, seed=cfg.seed)
    return {
        "n": int(len(d)), "events": int(yv.sum()), "event_rate": float(yv.mean()),
        "window": f"{d.index[0].date()} -> {d.index[-1].date()}",
        "brier": b, "brier_climatology": bc, "bss": 1 - b / bc if bc > 0 else None, "bss_ci90": [lo, hi],
        "log_loss": log_loss(p, yv), "log_loss_climatology": log_loss(pc, yv),
        "auc": auc(p, yv),
        "reliability": reliability(p, yv, cfg.bins),
    }


def current_estimate(F: pd.DataFrame, y: pd.Series, features: tuple[str, ...], horizon: int,
                     cfg: RiskConfig, rows: dict[str, pd.Series]) -> dict:
    """Fit on every label known today; probability + bootstrap 90% band for given rows."""
    X_all = F[list(features)].to_numpy(float)
    tr = ~np.isnan(X_all).any(axis=1) & y.notna().to_numpy()
    X, yt = X_all[tr], y.to_numpy(float)[tr]
    model = fit_logit(X, yt, cfg.l2, features)
    rng = np.random.default_rng(cfg.seed)
    n, block = len(yt), 12
    k = int(np.ceil(n / block))
    boots = []
    for _ in range(cfg.current_boot_reps):
        idx = np.concatenate([np.arange(s, s + block) for s in rng.integers(0, n - block + 1, k)])[:n]
        if 0 < yt[idx].sum() < len(idx):
            boots.append(fit_logit(X[idx], yt[idx], cfg.l2, features))
    out = {"fit_rows": int(n), "fit_events": int(yt.sum()), "base_rate": float(yt.mean()),
           "coef": {f: float(b) for f, b in zip(features, model.coef[1:])}, "intercept": float(model.coef[0])}
    for name, row in rows.items():
        x = row[list(features)].to_numpy(float)
        if np.isnan(x).any():
            out[name] = None
            continue
        p = float(model.predict(x[None, :])[0])
        bp = np.array([b.predict(x[None, :])[0] for b in boots])
        out[name] = {"date": str(row.name.date()), "p": p,
                     "ci90": [float(np.percentile(bp, 5)), float(np.percentile(bp, 95))] if len(bp) else None,
                     "contributions_logodds": model.contributions(x),
                     "features": {f: float(v) for f, v in zip(features, x)}}
    return out


# ---------------------------------------------------- volatility forecast
def vol_forecast(panel: pd.DataFrame, cfg: RiskConfig) -> dict:
    """Next-month realized volatility (rv21 at t+1) from log rv21 and log VIX
    at t; walk-forward OLS refit each January (labels known one month later).
    Contrast with the drawdown-event model: risk *magnitude* vs crash *events*."""
    complete = panel[~panel["partial"].astype(bool)]
    df = pd.DataFrame({"x_rv": np.log(complete["rv21"]), "x_vix": np.log(complete["vix"]),
                       "y": np.log(complete["rv21"]).shift(-1)}, index=complete.index).dropna(subset=["x_rv", "x_vix"])
    idx = df.index
    pred = pd.Series(np.nan, index=idx)
    naive = pd.Series(np.nan, index=idx)
    for Y in range(cfg.oos_start_year, int(idx[-1].year) + 1):
        train_end = pd.Timestamp(f"{Y - 1}-12-31")
        tr = (idx + pd.offsets.MonthEnd(1) <= train_end) & df["y"].notna().to_numpy()
        te = idx.year == Y
        if tr.sum() < cfg.min_train or not te.any():
            continue
        X = np.column_stack([np.ones(tr.sum()), df.loc[tr, ["x_rv", "x_vix"]].to_numpy()])
        beta, *_ = np.linalg.lstsq(X, df.loc[tr, "y"].to_numpy(), rcond=None)
        pred[te] = np.column_stack([np.ones(te.sum()), df.loc[te, ["x_rv", "x_vix"]].to_numpy()]) @ beta
        naive[te] = df.loc[tr, "y"].mean()
    ev = pd.DataFrame({"y": df["y"], "pred": pred, "naive": naive, "persist": df["x_rv"]}).dropna()
    sse = lambda a: float(np.sum((ev["y"] - ev[a]) ** 2))
    # Current forecast: fit on everything known now.
    tr = df["y"].notna()
    X = np.column_stack([np.ones(tr.sum()), df.loc[tr, ["x_rv", "x_vix"]].to_numpy()])
    beta, *_ = np.linalg.lstsq(X, df.loc[tr, "y"].to_numpy(), rcond=None)
    resid = df.loc[tr, "y"].to_numpy() - X @ beta
    q05, q95 = np.percentile(resid, [5, 95])
    def fc(row):
        z = float(beta[0] + beta[1] * np.log(row["rv21"]) + beta[2] * np.log(row["vix"]))
        return {"date": str(row.name.date()), "vol": float(np.exp(z)), "band90": [float(np.exp(z + q05)), float(np.exp(z + q95))],
                "current_rv21": float(row["rv21"])}
    current = {"month_end": fc(complete.iloc[-1])}
    if bool(panel["partial"].iloc[-1]) and pd.notna(panel["rv21"].iloc[-1]) and pd.notna(panel["vix"].iloc[-1]):
        current["provisional"] = fc(panel.iloc[-1])
    return {
        "target": "next-month realized volatility (21 trading days), log",
        "inputs": ["log rv21 (t)", "log VIX monthly mean (t)"],
        "n": int(len(ev)), "window": f"{ev.index[0].date()} -> {ev.index[-1].date()}",
        "oos_r2_vs_mean": 1 - sse("pred") / sse("naive"),
        "oos_r2_vs_persistence": 1 - sse("pred") / sse("persist"),
        "corr_pred_realized": float(np.corrcoef(ev["pred"], ev["y"])[0, 1]),
        "current": current,
        "series": {"dates": [str(d.date()) for d in ev.index],
                   "forecast": [round(float(np.exp(v)), 4) for v in ev["pred"]],
                   "realized": [round(float(np.exp(v)), 4) for v in ev["y"]]},
    }


def skill_verdict(ev: dict) -> str:
    """Pre-set display rule for the drawdown model."""
    bss, (lo, hi) = ev.get("bss"), ev.get("bss_ci90", [np.nan, np.nan])
    if bss is None or not np.isfinite(bss):
        return "insufficient data"
    if lo > 0:
        return "skillful: beats the base rate out-of-sample"
    if hi < 0:
        return "no skill: worse than the base rate out-of-sample - use the base rate"
    if bss <= 0:
        return "no demonstrated skill: not better than the base rate - use the base rate"
    return "inconclusive: positive but uncertain skill"


def run_risk(panel: pd.DataFrame, cfg: RiskConfig | None = None) -> dict:
    cfg = cfg or RiskConfig()
    complete = panel[~panel["partial"].astype(bool)]
    F = feature_frame(complete)
    first = F.dropna().index.min()
    F = F.loc[first:]
    risk_ret = complete["risk_ret"]
    last_year = int(F.index[-1].year)
    out = {"settings": {"features": FEATURES, "model": f"L2 logistic (lambda={cfg.l2}), standardized features",
                        "refit": "annually (January); labels must be fully known before the predicted year",
                        "oos_start_year": cfg.oos_start_year, "train_start": str(first.date()),
                        "drawdown_basis": "month-end closes of the risk asset (understates intra-month lows)",
                        "bootstrap": "12-month moving blocks"},
           "targets": []}
    partial_row = feature_frame(panel).iloc[-1] if bool(panel["partial"].iloc[-1]) else None
    for horizon, cut in cfg.targets:
        y = labels(risk_ret, horizon, cut).loc[first:]
        full_preds, full_folds = walk_forward(F, y, tuple(FEATURES), horizon, cfg, last_year)
        vol_preds, _ = walk_forward(F, y, VOL_ONLY, horizon, cfg, last_year)
        ev_full, ev_vol = evaluate(full_preds, cfg), evaluate(vol_preds, cfg)
        rows = {"month_end": F.iloc[-1]}
        if partial_row is not None:
            rows["provisional"] = partial_row
        cur = current_estimate(F, y, tuple(FEATURES), horizon, cfg, rows)
        oos = full_preds.loc[full_preds.index.year >= cfg.oos_start_year]
        out["targets"].append({
            "id": f"dd{int(abs(cut) * 100)}_{horizon}m",
            "label": f"P(drawdown worse than {cut:.0%} within {horizon} months)",
            "horizon": horizon, "cut": cut,
            "evaluation": {"full": ev_full, "vol_only": ev_vol},
            "verdict": skill_verdict(ev_full),
            "era_evaluation": era_table(full_preds),
            "folds": full_folds,
            "current": cur,
            "series": {
                "dates": [str(d.date()) for d in oos.index],
                "p_model": [None if pd.isna(v) else round(float(v), 4) for v in oos["p_model"]],
                "p_clim": [None if pd.isna(v) else round(float(v), 4) for v in oos["p_clim"]],
                "y": [None if pd.isna(v) else int(v) for v in oos["y"]],
            },
        })
    out["vol_forecast"] = vol_forecast(panel, cfg)
    return out


ERAS = {"2000-2002": ("2000-01-01", "2002-12-31"), "2003-2007": ("2003-01-01", "2007-12-31"),
        "2008+": ("2008-01-01", "2100-12-31")}


def era_table(preds: pd.DataFrame) -> list[dict]:
    d = preds.dropna(subset=["p_model", "p_clim", "y"])
    rows = []
    for name, (a, b) in ERAS.items():
        s = d.loc[a:b]
        if s.empty:
            continue
        yv = s["y"].to_numpy(float)
        bc = brier(s["p_clim"].to_numpy(float), yv)
        rows.append({"era": name, "n": int(len(s)), "events": int(yv.sum()),
                     "episodes": int(((s["y"] == 1) & (s["y"].shift(1, fill_value=0) == 0)).sum()),
                     "auc": auc(s["p_model"].to_numpy(float), yv),
                     "bss": 1 - brier(s["p_model"].to_numpy(float), yv) / bc if bc > 0 else None})
    return rows
