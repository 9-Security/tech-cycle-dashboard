"""Nested walk-forward, ablation, sensitivity and multiple-testing statistics.

Nested walk-forward (the headline result):
    For each test year Y, every grid configuration is scored on data from
    `train_start` through December of Y-1 only. The best configuration is
    then applied to year Y. Stitching the test years gives a genuinely
    out-of-sample (OOS) equity curve: no parameter ever saw the returns it is
    judged on.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from math import e, sqrt
from statistics import NormalDist

import numpy as np
import pandas as pd

from .backtest import SimResult, metrics, objective, simulate
from . import model_tilt
from .config import BacktestConfig, ParamGrid, RegimeParams, TiltGrid, TiltParams
from .regime import classify_arrays, weights_for

log = logging.getLogger(__name__)

SUBPERIODS = {
    "DotCom 2000-2002": ("2000-01-31", "2002-12-31"),
    "GFC 2008-2009": ("2008-01-31", "2009-12-31"),
    "COVID 2020": ("2020-01-31", "2020-12-31"),
    "Rate shock 2022": ("2022-01-31", "2022-12-31"),
    "AI Capex 2023+": ("2023-01-31", "2100-12-31"),
}


@dataclass
class BTData:
    """Backtest window of *complete* months plus one prior month of signals."""

    dates: pd.DatetimeIndex  # backtest months
    risk: np.ndarray
    safe: np.ndarray
    sig: dict[str, np.ndarray]  # each length n+1: [prior month, *backtest months]

    @property
    def n(self) -> int:
        return len(self.dates)

    @property
    def sig_vix(self) -> np.ndarray:
        return self.sig["vix"]

    @property
    def sig_oh(self) -> np.ndarray:
        return self.sig["overheat_score"]

    @property
    def sig_earn(self) -> np.ndarray:
        return self.sig["earn_score"]


SIGNAL_COLUMNS = ("vix", "overheat_score", "earn_score") + model_tilt.SIGNAL_COLUMNS


def prepare(panel: pd.DataFrame, bcfg: BacktestConfig) -> BTData:
    complete = panel[~panel["partial"].astype(bool)]
    start = complete.index.searchsorted(pd.Timestamp(bcfg.train_start))
    if start < 1:
        raise ValueError("train_start must leave one prior month for the initial weight")
    sig = complete.iloc[start - 1 :]
    bt = complete.iloc[start:]
    return BTData(
        dates=bt.index,
        risk=bt["risk_ret"].to_numpy(float),
        safe=bt["safe_ret"].to_numpy(float),
        sig={c: sig[c].to_numpy(float) for c in dict.fromkeys(SIGNAL_COLUMNS) if c in sig},
    )


Params = RegimeParams | TiltParams


def targets(bt: BTData, p: Params) -> tuple[np.ndarray, np.ndarray]:
    """(state codes, target weights) over [prior month, *backtest months]."""
    if isinstance(p, TiltParams):
        return model_tilt.targets(bt.sig, p)
    codes = classify_arrays(bt.sig_vix, bt.sig_oh, bt.sig_earn, p)
    return codes, weights_for(codes, p)


def run(bt: BTData, p: Params, cost_bps: float) -> tuple[np.ndarray, np.ndarray, SimResult]:
    codes, tgt = targets(bt, p)
    executed = tgt[:-1]  # executed[t] = target[t-1]
    return codes[1:], tgt[1:], simulate(bt.risk, bt.safe, executed, cost_bps)


@dataclass
class GridRun:
    params: list[Params]
    ret: np.ndarray  # K x n
    executed: np.ndarray  # K x n
    target: np.ndarray  # K x n (target decided at each backtest month-end)
    codes: np.ndarray  # K x n


def run_grid(bt: BTData, params: list[Params], cost_bps: float) -> GridRun:
    K, n = len(params), bt.n
    R = np.empty((K, n))
    E = np.empty((K, n))
    T = np.empty((K, n))
    C = np.empty((K, n), dtype=np.int8)
    for k, p in enumerate(params):
        codes, tgt, sim = run(bt, p, cost_bps)
        R[k], E[k], T[k], C[k] = sim.ret, sim.executed, tgt, codes
    return GridRun(params, R, E, T, C)


@dataclass
class WalkForward:
    dates: pd.DatetimeIndex
    executed: np.ndarray
    target: np.ndarray
    codes: np.ndarray
    sim: SimResult
    folds: list[dict] = field(default_factory=list)
    live_params: Params | None = None
    live_year: int | None = None


def nested_walk_forward(bt: BTData, grid: GridRun, bcfg: BacktestConfig, live_year: int) -> WalkForward:
    years = bt.dates.year
    first_oos = int(np.argmax(years >= bcfg.oos_start_year))
    if years[first_oos] < bcfg.oos_start_year:
        raise ValueError("no backtest months on/after oos_start_year")

    executed = np.full(bt.n, np.nan)
    target = np.full(bt.n, np.nan)
    codes = np.zeros(bt.n, dtype=np.int8)
    folds: list[dict] = []
    live_params = None

    for Y in range(bcfg.oos_start_year, live_year + 1):
        train_end = int(np.searchsorted(years, Y))  # exclusive: months with year < Y
        if train_end < bcfg.min_train_months:
            raise ValueError(f"fold {Y}: only {train_end} training months")
        scores = np.array(
            [objective(grid.ret[k, :train_end], bt.safe[:train_end], bcfg.mdd_budget, bcfg.mdd_penalty)
             for k in range(len(grid.params))]
        )
        k_best = int(np.argmax(scores))
        p = grid.params[k_best]
        test = np.flatnonzero(years == Y)
        if len(test):
            executed[test] = grid.executed[k_best, test]
            target[test] = grid.target[k_best, test]
            codes[test] = grid.codes[k_best, test]
            test_ret = grid.ret[k_best, test]
            test_ret_pct = float(np.prod(1 + test_ret) - 1)
        else:
            test_ret_pct = None
        train_m = metrics(grid.ret[k_best, :train_end], bt.safe[:train_end])
        folds.append({
            "test_year": Y,
            "train_months": train_end,
            "train_end": str(bt.dates[train_end - 1].date()),
            "params": p.to_dict(),
            "train_objective": float(scores[k_best]),
            "train_sharpe": train_m.get("sharpe"),
            "test_months": int(len(test)),
            "test_return": test_ret_pct,
        })
        live_params = p

    oos = slice(first_oos, bt.n)
    sim = simulate(bt.risk[oos], bt.safe[oos], executed[oos], bcfg.cost_bps)
    return WalkForward(
        dates=bt.dates[oos], executed=executed[oos], target=target[oos], codes=codes[oos],
        sim=sim, folds=folds, live_params=live_params, live_year=live_year,
    )


# ---------------------------------------------------------------- statistics
_N = NormalDist()
_EULER = 0.5772156649015329


def probabilistic_sharpe(sr: float, sr0: float, T: int, skew: float, kurt: float) -> float:
    """PSR (Bailey & Lopez de Prado). Inputs are per-period (monthly) Sharpe."""
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if T < 2 or denom <= 0:
        return float("nan")
    return float(_N.cdf((sr - sr0) * sqrt(T - 1) / sqrt(denom)))


def deflated_sharpe(sr_best: float, sr_trials: np.ndarray, T: int, skew: float, kurt: float) -> dict:
    trials = np.asarray(sr_trials, float)
    trials = trials[np.isfinite(trials)]
    N = len(trials)
    var = float(np.var(trials, ddof=1)) if N > 1 else 0.0
    if N < 2 or var <= 0:
        sr0 = 0.0
    else:
        sr0 = sqrt(var) * ((1 - _EULER) * _N.inv_cdf(1 - 1 / N) + _EULER * _N.inv_cdf(1 - 1 / (N * e)))
    return {
        "n_trials": N,
        "sr_best_monthly": sr_best,
        "sr0_monthly": sr0,
        "sr0_annualized": sr0 * sqrt(12),
        "dsr": probabilistic_sharpe(sr_best, sr0, T, skew, kurt),
    }


# ------------------------------------------------------------------ variants
INF = float("inf")


def variant_params(grid: ParamGrid, kind: str) -> list[RegimeParams]:
    base = list(grid)
    if kind == "full":
        out = base
    elif kind == "no_shock":
        out = [replace(p, vix_threshold=INF, w_shock=1.0) for p in base]
    elif kind == "no_overheat":
        out = [replace(p, overheat_threshold=INF, w_overheat=1.0) for p in base]
    elif kind == "no_digestion":
        out = [replace(p, earn_threshold=-INF, w_digestion=1.0) for p in base]
    elif kind == "shock_only":
        out = [replace(p, overheat_threshold=INF, earn_threshold=-INF, w_overheat=1.0, w_digestion=1.0) for p in base]
    else:
        raise ValueError(kind)
    return list(dict.fromkeys(out))  # dedupe, keep order


VARIANT_LABELS = {
    "full": "Full model (Shock + Overheat + Digestion)",
    "no_shock": "Without Shock (VIX)",
    "no_overheat": "Without Overheat (valuation + Capex)",
    "no_digestion": "Without Digestion (earnings)",
    "shock_only": "Shock (VIX) only",
}


def tilt_variant_params(grid: TiltGrid, kind: str) -> list[TiltParams]:
    base = list(grid)
    if kind == "full":
        out = base
    elif kind == "no_vol_target":
        out = [replace(p, vol_input="rv63", vol_target=INF) for p in base]
    elif kind == "no_price_ext":
        out = [replace(p, c_px=0.0) for p in base]
    elif kind == "no_pe":
        out = [replace(p, c_pe=0.0) for p in base]
    elif kind == "no_capex":
        out = [replace(p, c_capex=0.0) for p in base]
    elif kind == "no_earnings":
        out = [replace(p, earn_cut=1.0) for p in base]
    elif kind == "vol_target_only":
        out = [replace(p, c_px=0.0, c_pe=0.0, c_capex=0.0, earn_cut=1.0, base=1.0) for p in base]
    else:
        raise ValueError(kind)
    return list(dict.fromkeys(out))


TILT_VARIANT_LABELS = {
    "full": "Full v3 (price-ext + P/E + Capex tilts, earnings cut, vol target)",
    "no_vol_target": "Without vol targeting",
    "no_price_ext": "Without price-extension tilt",
    "no_pe": "Without P/E tilt",
    "no_capex": "Without Capex tilt",
    "no_earnings": "Without earnings cut",
    "vol_target_only": "Vol targeting only",
}


@dataclass
class ModelSpec:
    key: str
    label: str
    variants: dict[str, tuple[str, list]]  # kind -> (label, params); must include "full"
    sens_x: tuple[str, list]  # (param name, values)
    sens_y: tuple[str, list]


def regime_spec(grid: ParamGrid) -> ModelSpec:
    return ModelSpec(
        key="regime_v2", label="v2 regime model",
        variants={k: (VARIANT_LABELS[k], variant_params(grid, k)) for k in VARIANT_LABELS},
        sens_x=("overheat_threshold", list(grid.overheat_threshold)),
        sens_y=("vix_threshold", list(grid.vix_threshold)),
    )


def tilt_spec(grid: TiltGrid) -> ModelSpec:
    return ModelSpec(
        key="tilt_v3", label="v3 tilt + vol-target model",
        variants={k: (TILT_VARIANT_LABELS[k], tilt_variant_params(grid, k)) for k in TILT_VARIANT_LABELS},
        sens_x=("c_pe", sorted(grid.c_pe)),
        sens_y=("vol_target", sorted({vt for _, vt in grid.vol})),
    )


def subperiod_table(dates: pd.DatetimeIndex, series: dict[str, tuple[np.ndarray, np.ndarray]]) -> list[dict]:
    rows = []
    for name, (a, b) in SUBPERIODS.items():
        mask = (dates >= pd.Timestamp(a)) & (dates <= pd.Timestamp(b))
        if mask.sum() < 3:
            continue
        row = {"period": name, "start": str(dates[mask][0].date()), "end": str(dates[mask][-1].date())}
        for key, (ret, safe) in series.items():
            m = metrics(ret[mask], safe[mask])
            row[f"{key}_return"] = m["period_return"]
            row[f"{key}_max_dd"] = m["max_dd"]
            row[f"{key}_sharpe"] = m["sharpe"]
        rows.append(row)
    return rows


@dataclass
class ValidationRun:
    wf: WalkForward
    bh: SimResult
    insample_params: Params
    insample_ret_oos: np.ndarray
    report: dict


def full_validation(bt: BTData, spec: ModelSpec | ParamGrid, bcfg: BacktestConfig, live_year: int) -> ValidationRun:
    """Everything the dashboard's validation view needs, for one model."""
    if isinstance(spec, ParamGrid):
        spec = regime_spec(spec)
    cost = bcfg.cost_bps
    grid_params = spec.variants["full"][1]
    grid = run_grid(bt, grid_params, cost)
    wf = nested_walk_forward(bt, grid, bcfg, live_year)
    oos_mask = bt.dates >= wf.dates[0]
    safe_oos = bt.safe[oos_mask]
    risk_oos = bt.risk[oos_mask]

    bh = simulate(risk_oos, safe_oos, np.ones(len(risk_oos)), cost)
    m_oos = metrics(wf.sim.ret, safe_oos, wf.sim.executed, wf.sim.cost)
    m_bh = metrics(bh.ret, safe_oos, bh.executed, bh.cost)
    c = min(1.0, m_oos["ann_vol"] / m_bh["ann_vol"]) if m_bh["ann_vol"] > 0 else 1.0
    vm = simulate(risk_oos, safe_oos, np.full(len(risk_oos), c), cost)
    m_vm = metrics(vm.ret, safe_oos, vm.executed, vm.cost)

    # In-sample (hindsight) best: chosen on the whole sample, evaluated on OOS window.
    full_scores = np.array([objective(grid.ret[k], bt.safe, bcfg.mdd_budget, bcfg.mdd_penalty) for k in range(len(grid_params))])
    k_is = int(np.argmax(full_scores))
    p_is = grid_params[k_is]
    is_ret_oos = grid.ret[k_is, oos_mask]
    m_is_oos = metrics(is_ret_oos, safe_oos, grid.executed[k_is, oos_mask])
    m_is_full = metrics(grid.ret[k_is], bt.safe, grid.executed[k_is])

    # Multiple-testing: DSR of the in-sample best across all trials.
    sr_trials = np.array([metrics(grid.ret[k], bt.safe).get("sharpe_monthly", np.nan) for k in range(len(grid_params))])
    dsr = deflated_sharpe(m_is_full["sharpe_monthly"], sr_trials, bt.n, m_is_full["skew"], m_is_full["kurtosis"])
    psr_oos = probabilistic_sharpe(m_oos["sharpe_monthly"], 0.0, len(wf.sim.ret), m_oos["skew"], m_oos["kurtosis"])
    psr_oos_vs_bh = probabilistic_sharpe(m_oos["sharpe_monthly"], m_bh["sharpe_monthly"], len(wf.sim.ret), m_oos["skew"], m_oos["kurtosis"])

    # Ablation: each variant gets its own nested walk-forward.
    ablation = []
    for kind, (label, plist) in spec.variants.items():
        w = wf if kind == "full" else nested_walk_forward(bt, run_grid(bt, plist, cost), bcfg, live_year)
        m = metrics(w.sim.ret, safe_oos, w.sim.executed, w.sim.cost)
        ablation.append({"variant": kind, "label": label, **_pick(m)})
    ablation.append({"variant": "buy_hold", "label": "Buy & hold (XLK/NDX)", **_pick(m_bh)})
    ablation.append({"variant": "vol_matched_bh", "label": f"Vol-matched B&H ({c:.2f} risk / {1 - c:.2f} cash, ex-post)", **_pick(m_vm)})

    # Sensitivity: Sharpe over two parameters, others at in-sample best.
    (xn, xs), (yn, ys) = spec.sens_x, spec.sens_y
    heat = []
    for yv in ys:
        row = []
        for xv in xs:
            _, _, sim = run(bt, replace(p_is, **{xn: xv, yn: yv}), cost)
            row.append(metrics(sim.ret, bt.safe)["sharpe"])
        heat.append(row)

    subperiods = subperiod_table(wf.dates, {"strategy": (wf.sim.ret, safe_oos), "bh": (bh.ret, safe_oos)})

    report = {
        "model": {"key": spec.key, "label": spec.label},
        "summary": {
            "oos_start": str(wf.dates[0].date()),
            "oos_end": str(wf.dates[-1].date()),
            "oos_months": int(len(wf.dates)),
            "grid_size": len(grid_params),
            "objective": f"Sharpe - {bcfg.mdd_penalty} x max(0, MDD beyond {bcfg.mdd_budget:.0%})",
            "train_start": bcfg.train_start,
            "refit": f"every {bcfg.wf_step_months} months (January), expanding window",
        },
        "oos": _pick(m_oos),
        "bh": _pick(m_bh),
        "vol_matched_bh": {**_pick(m_vm), "risk_fraction": c},
        "insample_best": {
            "params": p_is.to_dict(),
            "full_sample": _pick(m_is_full),
            "on_oos_window": _pick(m_is_oos),
        },
        "stats": {
            "deflated_sharpe_insample": dsr,
            "psr_oos_vs_zero": psr_oos,
            "psr_oos_vs_bh_sharpe": psr_oos_vs_bh,
        },
        "ablation": ablation,
        "sensitivity": {
            "metric": "full-sample Sharpe (other params at in-sample best)",
            "x_name": xn, "x_values": xs, "y_name": yn, "y_values": ys,
            "sharpe": heat,
        },
        "subperiods": subperiods,
        "folds": wf.folds,
    }
    return ValidationRun(wf=wf, bh=bh, insample_params=p_is, insample_ret_oos=is_ret_oos, report=report)


def _pick(m: dict) -> dict:
    keys = ("sharpe", "sortino", "cagr", "ann_vol", "max_dd", "calmar", "final_nav",
            "period_return", "ann_turnover", "avg_weight", "total_cost", "months")
    return {k: m.get(k) for k in keys if k in m}


def valuation_comparison(panels: dict[str, pd.DataFrame], cfg_grid: ParamGrid, bcfg: BacktestConfig, live_year: int) -> list[dict]:
    """Same nested walk-forward under alternative valuation inputs, plus a
    simple information coefficient (valuation z vs next-12m log return of the
    risk asset) over the common window where firm-level P/E exists.
    Overlapping 12m windows: the IC is descriptive, not a significance test."""
    pe_panel = panels.get("pe")
    window = None
    if pe_panel is not None and (pe_panel["val_src"] == "PE").any():
        pe_idx = pe_panel.index[(pe_panel["val_src"] == "PE") & ~pe_panel["partial"].astype(bool)]
        window = (pe_idx[0], pe_idx[-1])
    rows = []
    for mode, panel in panels.items():
        bt = prepare(panel, bcfg)
        wf = nested_walk_forward(bt, run_grid(bt, variant_params(cfg_grid, "full"), bcfg.cost_bps), bcfg, live_year)
        m = metrics(wf.sim.ret, bt.safe[bt.dates >= wf.dates[0]], wf.sim.executed, wf.sim.cost)
        row = {"valuation": mode, "oos_sharpe": m["sharpe"], "oos_max_dd": m["max_dd"],
               "oos_final_nav": m["final_nav"], "overheat_months_oos": int((wf.codes == 1).sum()),
               "ic_val_z_fwd12m": None, "ic_window": None}
        if window is not None:
            c = panel[~panel["partial"].astype(bool)]
            logp = np.log1p(c["risk_ret"].fillna(0.0)).cumsum()
            fwd = (logp.shift(-12) - logp).loc[window[0]:window[1]]
            row["ic_val_z_fwd12m"] = float(c["val_z"].loc[window[0]:window[1]].corr(fwd))
            row["ic_window"] = f"{window[0].date()} -> {window[1].date()}"
        rows.append(row)
    return rows
