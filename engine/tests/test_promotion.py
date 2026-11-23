import numpy as np
import pandas as pd

from tcd.config import EngineConfig, PromotionRule
from tcd.promotion import evaluate, refresh_gaps, spec_fingerprint


def test_frozen_fingerprint_matches_current_spec():
    """Fails if any v3-relevant code or config changed without resetting the design date."""
    c = EngineConfig()
    assert spec_fingerprint(c.tilt_grid, c.features, c.backtest) == c.promotion.spec_fingerprint


def _run(n_post, v3_edge=0.004, fp_ok=True, gap=1):
    dates = pd.date_range("2000-01-31", "2026-11-30", freq="ME").append(
        pd.date_range("2026-12-31", periods=n_post, freq="ME")) if n_post else pd.date_range("2000-01-31", "2026-11-30", freq="ME")
    rng = np.random.default_rng(0)
    bh = rng.normal(0.008, 0.06, len(dates))
    v3 = 0.7 * bh + v3_edge
    rule = PromotionRule(spec_fingerprint="abc")
    return evaluate(dates=dates, v3_ret=v3, bh_ret=bh, safe=np.full(len(dates), 0.002),
                    full_v3_sharpe=0.46, full_bh_sharpe=0.39, design_date="2026-11-23", rule=rule,
                    current_fingerprint="abc" if fp_ok else "zzz", max_gap_days=gap)


def test_states():
    assert _run(0)["state"] == "collecting" and _run(0)["first_month"] == "2026-12"
    assert _run(0)["earliest_decision_after"] == "2028-11"
    assert _run(24)["state"] == "eligible"
    assert _run(24, v3_edge=-0.01)["state"] == "not_met"
    assert _run(36, v3_edge=-0.01)["state"] == "retire"
    assert _run(30, fp_ok=False)["state"] == "invalid"
    assert _run(24, gap=10)["state"] == "not_met"


def test_refresh_gaps(tmp_path):
    h = tmp_path / "history.csv"
    h.write_text("run_at\n20261201T221500Z\n20261202T221500Z\n20261212T221500Z\n")
    assert refresh_gaps(h, pd.Timestamp("2026-11-23"), pd.Timestamp("2026-12-13")) == 10
    assert refresh_gaps(tmp_path / "missing.csv", pd.Timestamp("2026-11-23"), pd.Timestamp("2026-12-13")) is None


def test_missing_evidence_is_undetermined_not_failed():
    import numpy as np
    import pandas as pd
    from tcd.config import PromotionRule
    from tcd.promotion import evaluate
    rule = PromotionRule()
    dates = pd.date_range("2026-12-31", periods=30, freq="ME")
    r = np.full(30, 0.01) + np.linspace(-0.001, 0.001, 30)
    out = evaluate(dates=dates, v3_ret=r * 1.2, bh_ret=r, safe=np.zeros(30), rule=rule, design_date="2026-11-23",
                   full_v3_sharpe=1.0, full_bh_sharpe=0.5, current_fingerprint=rule.spec_fingerprint, max_gap_days=None)
    assert out["state"] == "undetermined", out["state"]
