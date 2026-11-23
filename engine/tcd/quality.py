"""Data-quality gates. A FAIL aborts the refresh (fail-closed)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .fetch import RawData
from .validation import BTData


@dataclass
class Check:
    name: str
    status: str  # PASS | WARN | FAIL
    detail: str

    def to_dict(self) -> dict:
        return {"name": self.name, "status": self.status, "detail": self.detail}


class DataQualityError(RuntimeError):
    def __init__(self, checks: list[Check]):
        self.checks = checks
        failed = "; ".join(f"{c.name}: {c.detail}" for c in checks if c.status == "FAIL")
        super().__init__(f"data-quality gate failed: {failed}")


def run_checks(
    raw: RawData,
    panel: pd.DataFrame,
    bt: BTData,
    run_date: pd.Timestamp,
    max_staleness_days: int = 7,
    min_sec_names: int = 6,
) -> list[Check]:
    checks: list[Check] = []

    def add(name: str, ok: bool, detail: str, warn_only: bool = False) -> None:
        checks.append(Check(name, "PASS" if ok else ("WARN" if warn_only else "FAIL"), detail))

    last_obs = pd.Timestamp(panel.attrs["last_obs"])
    age = (run_date.normalize() - last_obs.normalize()).days
    add("market_freshness", age <= max_staleness_days, f"last market date {last_obs.date()} ({age}d old)")

    vix_last = raw.vix.index.max()
    add("vix_freshness", (last_obs - vix_last).days <= 3, f"last VIX date {vix_last.date()}")

    n_bad = {name: int(np.isnan(a).sum()) for name, a in
             (("risk", bt.risk), ("safe", bt.safe), ("vix", bt.sig_vix), ("overheat", bt.sig_oh), ("earn", bt.sig_earn))}
    add("no_missing_signals", sum(n_bad.values()) == 0, f"NaN counts {n_bad}")

    add("return_range", bool(np.nanmax(np.abs(bt.risk)) < 0.6), f"max |monthly return| {np.nanmax(np.abs(bt.risk)):.3f}")
    vmin, vmax = float(np.nanmin(bt.sig_vix)), float(np.nanmax(bt.sig_vix))
    add("vix_range", 5 <= vmin and vmax <= 100, f"VIX monthly range {vmin:.1f}-{vmax:.1f}")
    add("panel_length", bt.n >= 300, f"{bt.n} backtest months")

    complete = panel[~panel["partial"].astype(bool)]
    n_names = int(complete["n_capex_names"].iloc[-1])
    add("sec_coverage", n_names >= min_sec_names, f"{n_names}/10 names with valid TTM Capex at {complete.index[-1].date()}")

    latest_filed = max(
        (f["capex"]["filed"].max() for f in raw.sec_facts.values() if not f["capex"].empty),
        default=pd.NaT,
    )
    if pd.isna(latest_filed):
        add("sec_freshness", False, "no SEC filings parsed")
    else:
        sec_age = (run_date.normalize() - latest_filed.normalize()).days
        add("sec_freshness", sec_age <= 150, f"latest SEC Capex filing {latest_filed.date()} ({sec_age}d old)")

    if "n_pe_names" in complete:
        n_pe = int(complete["n_pe_names"].iloc[-1])
        add("pe_coverage", n_pe >= min_sec_names, f"{n_pe}/10 names in aggregate P/E at {complete.index[-1].date()}")
        pe = float(complete["pe_agg"].iloc[-1])
        add("pe_range", 5 <= pe <= 150, f"aggregate P/E {pe:.1f}")

    src = complete["capex_src"].iloc[-1]
    add("capex_source_current", src == "SEC", f"latest capex signal source = {src}")

    for w in raw.warnings:
        checks.append(Check("fetch_warning", "WARN", w))
    return checks


def enforce(checks: list[Check]) -> None:
    if any(c.status == "FAIL" for c in checks):
        raise DataQualityError(checks)
