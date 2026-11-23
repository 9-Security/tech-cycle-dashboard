import numpy as np
import pandas as pd

from tcd.risk_model import (RiskConfig, auc, brier, fit_logit, labels, reliability, skill_verdict, walk_forward)


def test_logit_recovers_direction_and_calibration():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(5000, 1))
    p_true = 1 / (1 + np.exp(-(-1.5 + 1.0 * x[:, 0])))
    y = (rng.uniform(size=5000) < p_true).astype(float)
    m = fit_logit(x, y, l2=0.0, features=("x",))
    assert abs(m.coef[1] / x.std() - 1.0) < 0.15
    assert abs(m.predict(x).mean() - y.mean()) < 0.01


def test_metrics():
    y = np.array([0, 0, 1, 1.0])
    assert auc(np.array([0.1, 0.2, 0.8, 0.9]), y) == 1.0
    assert auc(np.array([0.9, 0.8, 0.2, 0.1]), y) == 0.0
    assert np.isclose(brier(np.full(4, 0.5), y), 0.25)
    rel = reliability(np.array([0.01, 0.02, 0.6, 0.7]), y, (0.0, 0.5, 1.0))
    assert [r["n"] for r in rel] == [2, 2] and rel[1]["observed"] == 1.0


def test_labels_are_forward_looking():
    idx = pd.date_range("2000-01-31", periods=6, freq="ME")
    r = pd.Series([0.0, 0.0, -0.3, 0.0, 0.0, 0.0], index=idx)
    y = labels(r, 2, -0.2)
    assert y.iloc[0] == 1.0 and y.iloc[1] == 1.0 and y.iloc[2] == 0.0
    assert y.iloc[-2:].isna().all()


def test_walk_forward_trains_only_on_fully_known_labels():
    idx = pd.date_range("1990-01-31", "2005-12-31", freq="ME")
    rng = np.random.default_rng(3)
    F = pd.DataFrame({"a": rng.normal(size=len(idx))}, index=idx)
    y = pd.Series((rng.uniform(size=len(idx)) < 0.3).astype(float), index=idx)
    cfg = RiskConfig(oos_start_year=2000, min_train=24, min_positives=3)
    p1, folds1 = walk_forward(F, y, ("a",), 12, cfg, 2005)
    # Changing labels that are not yet known at each fold must not change that fold.
    y2 = y.copy()
    y2.loc["2002-01-31":] = 1 - y2.loc["2002-01-31":]
    p2, folds2 = walk_forward(F, y2, ("a",), 12, cfg, 2005)
    # Fold 2003 trains on t + 12m <= 2002-12-31, i.e. t <= 2001-12: unchanged.
    pd.testing.assert_series_equal(p1.loc[:"2003-12-31", "p_model"], p2.loc[:"2003-12-31", "p_model"])
    assert not np.allclose(p1.loc["2004", "p_model"], p2.loc["2004", "p_model"])
    assert folds1[3]["n_train"] == folds2[3]["n_train"]


def test_skill_verdict_rule():
    assert skill_verdict({"bss": 0.1, "bss_ci90": [0.02, 0.2]}).startswith("skillful")
    assert skill_verdict({"bss": -0.2, "bss_ci90": [-0.4, -0.05]}).startswith("no skill")
    assert skill_verdict({"bss": -0.05, "bss_ci90": [-0.2, 0.1]}).startswith("no demonstrated skill")
    assert skill_verdict({"bss": 0.05, "bss_ci90": [-0.1, 0.2]}).startswith("inconclusive")
