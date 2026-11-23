"""v3 continuous exposure model.

    base_w  = clip(base + c_px * px_z + c_pe * pe_z + c_capex * capex_z, 0, 1)
    base_w *= earn_cut   if earn_score < earn_threshold
    scale   = min(1, vol_target / sigma_hat)          (sigma from rv21 / rv63 / VIX)
    target  = clip(base_w * scale, 0, 1), then a no-trade band

No leverage. Signs of c_px / c_pe / c_capex are chosen by walk-forward, not
fixed. Price extension (momentum-like, full history) and aggregate P/E (2013+)
are separate variables with separate coefficients; P/E counts as 0 before it
exists, so its coefficient is learned only from P/E-era training data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import TiltParams

STATE_LABELS = {1: "Valuation/Capex cut", 2: "Vol-capped", 3: "Earnings cut", 4: "Unconstrained"}
STATE_COLORS = {1: "#c45c26", 2: "#8b1e3f", 3: "#b08900", 4: "#2f6f4e"}
VOL_COLUMNS = {"rv21": "rv21", "rv63": "rv63", "vix": "vol_vix"}
SIGNAL_COLUMNS = ("val_z_proxy", "val_z_pe", "capex_z", "earn_score", "rv21", "rv63", "vol_vix")


def components(sig: pd.DataFrame | dict, p: TiltParams) -> dict[str, np.ndarray]:
    px = np.nan_to_num(np.asarray(sig["val_z_proxy"], float))
    pe = np.nan_to_num(np.asarray(sig["val_z_pe"], float))
    capex = np.nan_to_num(np.asarray(sig["capex_z"], float))
    earn = np.asarray(sig["earn_score"], float)
    tilt = p.c_px * px + p.c_pe * pe + p.c_capex * capex
    base_w = np.clip(p.base + tilt, 0.0, 1.0)
    with np.errstate(invalid="ignore"):
        earn_hit = (earn < p.earn_threshold) & (p.earn_cut < 1.0)
    base_w = np.where(earn_hit, base_w * p.earn_cut, base_w)
    sigma = np.asarray(sig[VOL_COLUMNS[p.vol_input]], float)
    if np.isfinite(p.vol_target):
        with np.errstate(divide="ignore", invalid="ignore"):
            scale = np.where(np.isfinite(sigma) & (sigma > 0), np.minimum(1.0, p.vol_target / sigma), 1.0)
    else:
        scale = np.ones_like(base_w)
    raw = np.clip(base_w * scale, 0.0, 1.0)
    return {"tilt": tilt, "base_w": base_w, "earn_hit": earn_hit, "sigma": sigma, "scale": scale, "raw": raw}


def apply_band(raw: np.ndarray, band: float) -> np.ndarray:
    w = np.empty_like(raw)
    w[0] = raw[0]
    for i in range(1, len(raw)):
        w[i] = raw[i] if abs(raw[i] - w[i - 1]) >= band else w[i - 1]
    return w


def states(c: dict[str, np.ndarray], p: TiltParams) -> np.ndarray:
    """Descriptive state of the binding constraint (for the timeline)."""
    st = np.full(len(c["raw"]), 4, dtype=np.int8)
    st[c["tilt"] < -0.05] = 1
    st[c["earn_hit"]] = 3
    st[c["scale"] < 0.9] = 2
    return st


def targets(sig: pd.DataFrame | dict, p: TiltParams) -> tuple[np.ndarray, np.ndarray]:
    c = components(sig, p)
    return states(c, p), apply_band(c["raw"], p.band)
