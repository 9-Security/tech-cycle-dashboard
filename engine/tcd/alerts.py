"""Risk alerts (methodology section 21).

Compares this refresh with the previously published state and lists events
that happened on a NEW US close (a same-day re-run cannot repeat them):

    light_change        risk light level changed
    cap_band_change     exposure-cap band changed
    var_breach          a live 1-day VaR was newly scored as breached
    validation_warning  an interim look newly reads too_many_at_N

The workflow posts the events of this run as a comment on the open
`risk-alert` issue. Only codes, dates and numbers are written.
"""
from __future__ import annotations

RECENT_MAX = 100
WATCHED = ("var_1d", "var_1d_challenger")


def _verdicts(review: dict | None) -> dict:
    review = review or {}
    out = {t: (((review.get("targets") or {}).get(t) or {}).get("interim") or {}).get("verdict") for t in WATCHED}
    out["panel"] = (((review.get("panel") or {}).get("interim")) or {}).get("verdict")
    return out


def events(prev_status: dict | None, light: dict, cap: dict | None,
           prev_review: dict | None, review: dict | None) -> list[dict]:
    ev = []
    pl = (prev_status or {}).get("light") or {}
    new_close = bool(pl.get("date")) and str(light["date"]) > str(pl["date"])
    if new_close and pl.get("level") and pl["level"] != light["level"]:
        ev.append({"type": "light_change", "date": light["date"], "from": pl["level"], "to": light["level"],
                   "vol_percentile": light.get("vol_percentile")})
    pc = (prev_status or {}).get("exposure_cap") or {}
    if cap and pc.get("band") and pc.get("date") and str(cap["date"]) > str(pc["date"]) and pc["band"] != cap["band"]:
        ev.append({"type": "cap_band_change", "date": cap["date"], "from": pc["band"], "to": cap["band"],
                   "cap_from": pc.get("cap"), "cap_to": cap["cap"]})
    for b in ((review or {}).get("last_run") or {}).get("new_var_breaches") or []:
        ev.append({"type": "var_breach", **b})
    old, new = _verdicts(prev_review), _verdicts(review)
    for k, v in new.items():
        if v and v.startswith("too_many") and not (old.get(k) or "").startswith("too_many"):
            ev.append({"type": "validation_warning", "series": k, "verdict": v})
    return ev


def merge(prev: dict | None, ev: list[dict], as_of: str) -> dict:
    recent = list((prev or {}).get("recent") or [])
    recent = (recent + [{**e, "run": as_of} for e in ev])[-RECENT_MAX:]
    return {"as_of": as_of, "events": ev, "recent": recent}


def describe(e: dict) -> str:
    """One plain English line per event (issue comment)."""
    t = e["type"]
    if t == "light_change":
        return f"- Risk light {e['from']} -> {e['to']} at the {e['date']} close."
    if t == "cap_band_change":
        return (f"- Suggested max exposure band {e['from']} -> {e['to']} at the {e['date']} close "
                f"({_pct(e.get('cap_from'))} -> {_pct(e.get('cap_to'))}).")
    if t == "var_breach":
        return (f"- 1-day 95% VaR breached on {e['target_end']}: return {_pct(e.get('ret'), 2)} vs VaR "
                f"-{_pct(e.get('var95'), 2)} (forecast from the {e['origin_date']} close).")
    if t == "validation_warning":
        return f"- Interim look warning for {e['series']}: {e['verdict']} (too many VaR breaches)."
    return f"- {t}"


def _pct(x, d: int = 0) -> str:
    return "n/a" if x is None else f"{float(x) * 100:.{d}f}%"
