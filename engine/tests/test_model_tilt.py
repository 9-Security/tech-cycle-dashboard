import numpy as np
import pandas as pd

from tcd import model_tilt
from tcd.config import TiltGrid, TiltParams


def _sig(n=5, **over):
    base = {c: np.zeros(n) for c in model_tilt.SIGNAL_COLUMNS}
    base["rv21"] = base["rv63"] = base["vol_vix"] = np.full(n, 0.20)
    base.update({k: np.asarray(v, float) for k, v in over.items()})
    return base


def test_weights_bounded_no_leverage():
    sig = _sig(4, val_z_proxy=[5, -5, 0, 10])
    _, w = model_tilt.targets(sig, TiltParams(c_px=0.25, band=0.0))
    assert np.all((w >= 0) & (w <= 1))
    assert w[0] == 1.0 and w[1] == 0.0


def test_vol_target_scales_down_only():
    sig = _sig(3, rv63=[0.10, 0.40, np.nan])
    c = model_tilt.components(sig, TiltParams(vol_input="rv63", vol_target=0.20))
    assert np.allclose(c["scale"], [1.0, 0.5, 1.0])  # never levers up; missing vol -> no scaling


def test_pe_missing_counts_as_zero():
    sig = _sig(2, val_z_pe=[np.nan, 2.0])
    c = model_tilt.components(sig, TiltParams(c_pe=-0.25, base=1.0))
    assert np.allclose(c["base_w"], [1.0, 0.5])


def test_earnings_cut():
    sig = _sig(2, earn_score=[-2.0, 0.0])
    c = model_tilt.components(sig, TiltParams(earn_cut=0.75, earn_threshold=-1.0))
    assert np.allclose(c["base_w"], [0.75, 1.0])


def test_no_trade_band():
    w = model_tilt.apply_band(np.array([0.50, 0.53, 0.60, 0.62]), 0.05)
    assert w.tolist() == [0.50, 0.50, 0.60, 0.60]


def test_grid_prefers_simplest_on_ties():
    first = next(iter(TiltGrid()))
    assert first.c_px == first.c_pe == first.c_capex == 0.0 and first.base == 1.0 and first.earn_cut == 1.0
    assert len(TiltGrid()) == len(list(TiltGrid()))
