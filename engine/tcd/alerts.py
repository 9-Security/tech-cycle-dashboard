"""Risk alerts (methodology section 21).

Compares this refresh with the previously published state and lists events
that happened on a NEW US close (a same-day re-run cannot repeat them):

    light_change        risk light level changed and held for CONFIRM_CLOSES closes
    cap_band_change     exposure-cap band changed and held for CONFIRM_CLOSES closes
    var_breach          a live 1-day VaR was newly scored as breached
    validation_warning  an interim look newly reads too_many_at_N

The workflow posts the events of this run as a comment on the open
`risk-alert` issue. Only codes, dates and numbers are written.
"""
from __future__ import annotations

RECENT_MAX = 100
CONFIRM_CLOSES = 2  # option A (methodology section 21, amendment 1): alerts only, display unchanged
WATCHED = ("var_1d", "var_1d_challenger")


def _verdicts(review: dict | None) -> dict:
    review = review or {}
    out = {t: (((review.get("targets") or {}).get(t) or {}).get("interim") or {}).get("verdict") for t in WATCHED}
    out["panel"] = (((review.get("panel") or {}).get("interim")) or {}).get("verdict")
    return out


def step(state: dict | None, date: str, level: str) -> tuple[dict, tuple[str, str] | None]:
    """Confirmation filter for one series. A change is reported only after the
    new level has held for CONFIRM_CLOSES consecutive closes; the reference is
    the last CONFIRMED level, not yesterday's level. Same or older date: no-op."""
    if not state or not state.get("confirmed"):
        return {"confirmed": level, "candidate": None, "count": 0, "last_date": date}, None
    if str(date) <= str(state.get("last_date") or ""):
        return state, None
    st = {**state, "last_date": date}
    if level == st["confirmed"]:
        st.update(candidate=None, count=0)
        return st, None
    st["count"] = st["count"] + 1 if level == st.get("candidate") else 1
    st["candidate"] = level
    if st["count"] >= CONFIRM_CLOSES:
        frm = st["confirmed"]
        st.update(confirmed=level, candidate=None, count=0)
        return st, (frm, level)
    return st, None


def confirmed_changes(levels) -> list[tuple]:
    """Apply `step` to a (date, level) sequence: [(date, from, to), ...]."""
    st, out = None, []
    for d, lv in levels:
        if lv is None:
            continue
        st, ch = step(st, str(d), lv)
        if ch:
            out.append((d, *ch))
    return out


def _seed(prev_alerts: dict | None, prev_status: dict | None, key: str, skey: str, field: str) -> dict | None:
    """Filter state from the last run; on the first run, start from the previously
    published level (so the switch to confirmation does not raise an alert)."""
    st = ((prev_alerts or {}).get("state") or {}).get(key)
    if st:
        return st
    p = (prev_status or {}).get(skey) or {}
    if p.get(field) and p.get("date"):
        return {"confirmed": p[field], "candidate": None, "count": 0, "last_date": p["date"]}
    return None


def events(prev_status: dict | None, light: dict, cap: dict | None,
           prev_review: dict | None, review: dict | None, prev_alerts: dict | None = None) -> tuple[list[dict], dict]:
    """Returns (events of this run, filter state to store)."""
    ev, state = [], {}
    st, ch = step(_seed(prev_alerts, prev_status, "light", "light", "level"), light["date"], light["level"])
    state["light"] = st
    if ch:
        ev.append({"type": "light_change", "date": light["date"], "from": ch[0], "to": ch[1],
                   "confirmed_closes": CONFIRM_CLOSES, "vol_percentile": light.get("vol_percentile")})
    if cap:
        st, ch = step(_seed(prev_alerts, prev_status, "cap", "exposure_cap", "band"), cap["date"], cap["band"])
        state["cap"] = st
        if ch:
            ev.append({"type": "cap_band_change", "date": cap["date"], "from": ch[0], "to": ch[1],
                       "confirmed_closes": CONFIRM_CLOSES, "cap_to": cap["cap"]})
    for b in ((review or {}).get("last_run") or {}).get("new_var_breaches") or []:
        ev.append({"type": "var_breach", **b})
    old, new = _verdicts(prev_review), _verdicts(review)
    for k, v in new.items():
        if v and v.startswith("too_many") and not (old.get(k) or "").startswith("too_many"):
            ev.append({"type": "validation_warning", "series": k, "verdict": v})
    return ev, state


def merge(prev: dict | None, ev: list[dict], as_of: str, state: dict | None = None) -> dict:
    recent = list((prev or {}).get("recent") or [])
    recent = (recent + [{**e, "run": as_of} for e in ev])[-RECENT_MAX:]
    return {"as_of": as_of, "events": ev, "recent": recent,
            "state": state if state is not None else (prev or {}).get("state") or {}}


def describe(e: dict) -> str:
    """One plain English line per event (issue comment)."""
    t = e["type"]
    if t == "light_change":
        return f"- Risk light {e['from']} -> {e['to']} (held {e.get('confirmed_closes', 1)} closes, to {e['date']})."
    if t == "cap_band_change":
        return (f"- Suggested max exposure band {e['from']} -> {e['to']} (held {e.get('confirmed_closes', 1)} closes, "
                f"to {e['date']}; cap now {_pct(e.get('cap_to'))}).")
    if t == "var_breach":
        return (f"- 1-day 95% VaR breached on {e['target_end']}: return {_pct(e.get('ret'), 2)} vs VaR "
                f"-{_pct(e.get('var95'), 2)} (forecast from the {e['origin_date']} close).")
    if t == "validation_warning":
        return f"- Interim look warning for {e['series']}: {e['verdict']} (too many VaR breaches)."
    return f"- {t}"


def _pct(x, d: int = 0) -> str:
    return "n/a" if x is None else f"{float(x) * 100:.{d}f}%"
