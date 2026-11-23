"""Regime classification. Priority: Shock -> Overheat -> Digestion -> Normal."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import RegimeParams

SIGNAL_COLUMNS = ("vix", "overheat_score", "earn_score")


def classify_arrays(vix: np.ndarray, overheat: np.ndarray, earn: np.ndarray, p: RegimeParams) -> np.ndarray:
    # NaN comparisons are False -> a missing signal never triggers a defense.
    with np.errstate(invalid="ignore"):
        shock = vix > p.vix_threshold
        hot = overheat > p.overheat_threshold
        digest = earn < p.earn_threshold
    return np.where(shock, 2, np.where(hot, 1, np.where(digest, 3, 4))).astype(np.int8)


def weights_for(codes: np.ndarray, p: RegimeParams) -> np.ndarray:
    lut = np.array([np.nan, p.w_overheat, p.w_shock, p.w_digestion, p.w_normal])
    return lut[codes]


def classify(panel: pd.DataFrame, p: RegimeParams) -> pd.DataFrame:
    codes = classify_arrays(
        panel["vix"].to_numpy(float),
        panel["overheat_score"].to_numpy(float),
        panel["earn_score"].to_numpy(float),
        p,
    )
    return pd.DataFrame({"regime": codes, "target_weight": weights_for(codes, p)}, index=panel.index)
