from datetime import datetime, timezone

import numpy as np
import pandas as pd

from tcd import alerts, exposure
from tcd import market_ledger as M


def test_cap_rounds_down_to_five_points_and_never_exceeds_one():
    assert exposure.cap_for(0.19, 0.53)[1] == 0.35
    assert exposure.cap_for(0.20, 0.40)[1] == 0.50  # exact step is kept
    assert exposure.cap_for(0.30, 0.10) == (1.0, 1.0)
    assert [exposure.band_for(c) for c in (1.0, 0.95, 0.75, 0.70, 0.5, 0.45, 0.25, 0.2)] == list("ABBCCDDE")


def test_stability_counts_whipsaws():
    s = pd.Series(list("AAABAAAACCCCCCCCA"))
    st = exposure.stability(s)
    # changes: A->B, B->A (reversal of the first within 5 days), A->C, C->A
    assert st["changes"] == 4 and abs(st["whipsaw_share"] - 0.25) < 1e-12


LIGHT_PREV = {"light": {"date": "2026-11-20", "level": "red"},
              "exposure_cap": {"date": "2026-11-20", "band": "D", "cap": 0.35}}


def test_events_only_on_a_new_close():
    light = {"date": "2026-11-23", "level": "yellow", "vol_percentile": 0.7}
    cap = {"date": "2026-11-23", "band": "C", "cap": 0.55}
    ev = alerts.events(LIGHT_PREV, light, cap, None, None)
    assert [e["type"] for e in ev] == ["light_change", "cap_band_change"]
    # Same close re-run: nothing repeats.
    same = alerts.events({"light": {**light, "level": "red"}, "exposure_cap": {**cap, "band": "D"}}, light, cap, None, None)
    assert same == []
    # First run (no previous state): nothing.
    assert alerts.events(None, light, cap, None, None) == []


def test_breaches_and_new_validation_warnings():
    light = {"date": "2026-11-20", "level": "red"}
    old = {"targets": {"var_1d": {"interim": {"verdict": "before_first_look"}}}, "panel": {"interim": {"verdict": "too_many_at_60"}}}
    new = {"targets": {"var_1d": {"interim": {"verdict": "too_many_at_60"}}}, "panel": {"interim": {"verdict": "too_many_at_60"}},
           "last_run": {"new_var_breaches": [{"origin_date": "a", "target_end": "b", "var95": 0.05, "ret": -0.06}]}}
    ev = alerts.events(LIGHT_PREV, light, None, old, new)
    assert [e["type"] for e in ev] == ["var_breach", "validation_warning"] and ev[1]["series"] == "var_1d"
    assert all(alerts.describe(e).startswith("- ") for e in ev)


def test_merge_keeps_a_bounded_history():
    a = None
    for i in range(alerts.RECENT_MAX + 5):
        a = alerts.merge(a, [{"type": "light_change", "date": str(i), "from": "red", "to": "green"}], f"r{i}")
    assert len(a["recent"]) == alerts.RECENT_MAX and a["recent"][-1]["run"] == f"r{alerts.RECENT_MAX + 4}"
    assert alerts.merge(a, [], "x")["events"] == []


SHORT = {"date": "2024-01-02", "model": "har_vix", "var95_1d_simple_ret": 0.03, "vol_1d": 0.01, "vol_5d": 0.0224,
         "ewma_vol_ann": 0.18, "vol_5d_ann": 0.40, "vol_hist_median": 0.20}


def test_cap_row_logged_and_scored(tmp_path):
    cap = exposure.current(SHORT)
    after = datetime(2024, 1, 2, 22, 15, tzinfo=timezone.utc)
    rows = M.forecast_rows(SHORT, {}, "red", "t", after, "x", cap=cap)
    row = {r["target"]: r for r in rows}["exposure_cap_5d"]
    assert row["band_hi"] == "0.50" and row["level"] == "C" and row["model_id"] == M.exposure_model_id("har_vix")
    p = tmp_path / "l.csv"
    M.append_ledger(p, rows, M.COLUMNS, ("target", "origin_date"))
    led = M._read(p, M.COLUMNS)
    days = pd.bdate_range("2024-01-02", periods=7)
    r = pd.Series([0.0, 0.02, -0.02, 0.02, -0.02, 0.02, 0.0], index=days)
    oc = M.evaluate(led, r, pd.DataFrame({"rv21": [], "partial": []}), set()).set_index("target")
    want = 0.5 * np.sqrt(0.02 ** 2 * 252) / 0.20
    assert oc.loc["exposure_cap_5d", "status"] == "scored" and abs(oc.loc["exposure_cap_5d", "ratio"] - want) < 1e-9
    assert bool(oc.loc["exposure_cap_5d", "in_band"]) == (want <= M.CAP_OVERSHOOT)


def test_cap_row_skipped_when_dates_differ():
    cap = {**exposure.current(SHORT), "date": "2024-01-01"}
    rows = M.forecast_rows(SHORT, {}, "red", "t", datetime(2024, 1, 2, 22, 15, tzinfo=timezone.utc), "x", cap=cap)
    assert "exposure_cap_5d" not in {r["target"] for r in rows}
