"""Point-in-time (PIT) fundamentals from SEC XBRL facts.

Rules (no look-ahead):
1. For every reporting period (start, end) keep the FIRST-REPORTED value and
   its `filed` date. Later restatements are ignored, because they were not
   known at the time.
2. Quarterly values come from ~3-month facts directly, or are derived as the
   difference of two year-to-date facts with the same start date
   (e.g. 9M - 6M = Q3, FY - 9M = Q4). A derived quarter becomes available on
   the later of the two filing dates.
3. At each month-end, a company's TTM value uses only quarters whose
   availability date is on or before that month-end.
4. Aggregates across companies are chain-linked over the set of names valid in
   both consecutive months, so a name entering the sample (IPO, new CIK, XBRL
   start) does not create an artificial jump.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

QUARTER_DAYS = (80, 100)


def first_reported(facts: pd.DataFrame) -> pd.DataFrame:
    """One row per (start, end): earliest filing, tag priority breaks ties."""
    if facts.empty:
        return facts.assign(available=pd.Series(dtype="datetime64[ns]"))
    df = facts.sort_values(["start", "end", "filed", "priority"])
    df = df.drop_duplicates(["start", "end"], keep="first").copy()
    df["available"] = df["filed"]
    return df[["start", "end", "val", "available"]].reset_index(drop=True)


def quarterly(facts: pd.DataFrame) -> pd.DataFrame:
    """Derive quarterly values. Returns columns end, val, available (sorted by end)."""
    rec = first_reported(facts)
    if rec.empty:
        return pd.DataFrame(columns=["end", "val", "available"])
    rec["dur"] = (rec["end"] - rec["start"]).dt.days
    lo, hi = QUARTER_DAYS

    direct = rec[rec["dur"].between(lo, hi)]
    out: dict[pd.Timestamp, tuple[float, pd.Timestamp]] = {}
    for r in direct.sort_values("available").itertuples():
        out.setdefault(r.end, (r.val, r.available))

    # Year-to-date differencing within the same fiscal-year start.
    for start, grp in rec.groupby("start"):
        grp = grp.sort_values("end")
        ends = list(grp.itertuples())
        for i, cur in enumerate(ends):
            if cur.dur <= hi or cur.end in out:
                continue
            for prev in ends[:i][::-1]:
                gap = (cur.end - prev.end).days
                if lo <= gap <= hi:
                    out[cur.end] = (cur.val - prev.val, max(cur.available, prev.available))
                    break

    q = pd.DataFrame(
        [(e, v, a) for e, (v, a) in out.items()], columns=["end", "val", "available"]
    ).sort_values("end")
    return q.reset_index(drop=True)


def monthly_ttm(q: pd.DataFrame, months: pd.DatetimeIndex, stale_days: int = 200) -> pd.Series:
    """TTM sum known at each month-end (NaN when not computable)."""
    out = pd.Series(np.nan, index=months, dtype=float)
    if q.empty:
        return out
    q = q.sort_values("end")
    lo, hi = QUARTER_DAYS
    for m in months:
        known = q[q["available"] <= m]
        if len(known) < 4:
            continue
        last4 = known.sort_values("end").iloc[-4:]
        ends = last4["end"].tolist()
        if (m - ends[-1]).days > stale_days:
            continue
        gaps = [(b - a).days for a, b in zip(ends, ends[1:])]
        if not all(lo <= g <= hi for g in gaps):
            continue
        out[m] = float(last4["val"].sum())
    return out


def chain_link(
    num: pd.DataFrame,
    den: pd.DataFrame | None = None,
    min_names: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """Chain-linked aggregate.

    If `den` is given the level tracks sum(num)/sum(den) (a ratio);
    otherwise it tracks sum(num). Returns (level, n_names).
    """
    valid = num.notna()
    if den is not None:
        valid &= den.notna() & (den > 0)
    n = valid.sum(axis=1)
    level = pd.Series(np.nan, index=num.index, dtype=float)

    def agg(row: pd.Timestamp, cols: pd.Index) -> float:
        s_num = num.loc[row, cols].sum()
        if den is None:
            return float(s_num)
        s_den = den.loc[row, cols].sum()
        return float(s_num / s_den) if s_den > 0 else np.nan

    prev_row = None
    for row in num.index:
        cols_now = valid.columns[valid.loc[row]]
        if prev_row is None or np.isnan(level[prev_row]):
            if len(cols_now) >= min_names:
                level[row] = agg(row, cols_now)
                prev_row = row
            continue
        common = cols_now.intersection(valid.columns[valid.loc[prev_row]])
        if len(common) < min_names:
            level[row] = np.nan
            prev_row = row
            continue
        a, b = agg(prev_row, common), agg(row, common)
        if not np.isfinite(a) or not np.isfinite(b) or a <= 0:
            level[row] = level[prev_row]  # cannot link; hold level (growth = 0)
        else:
            level[row] = level[prev_row] * b / a
        prev_row = row
    level[n < min_names] = np.nan
    return level, n


def split_factor_after(splits: pd.Series, when: pd.Timestamp) -> float:
    """Product of split ratios strictly after `when` (filing date)."""
    if splits is None or splits.empty:
        return 1.0
    return float(splits[splits.index > when].prod())


def monthly_shares(facts: pd.DataFrame, splits: pd.Series, months: pd.DatetimeIndex, stale_days: int = 200) -> pd.Series:
    """Share count known at each month-end, expressed on Yahoo's current split basis.

    A filing already reflects splits that happened before it was issued
    (ASC 260 retroactive adjustment), so only splits AFTER the filing date
    are applied.
    """
    out = pd.Series(np.nan, index=months, dtype=float)
    if facts.empty:
        return out
    # One value per period end: preferred tag, then its earliest (first-reported) filing.
    rec = facts.sort_values(["end", "priority", "filed"]).drop_duplicates("end", keep="first").copy()
    rec["adj"] = [v * split_factor_after(splits, f) for v, f in zip(rec["val"], rec["filed"])]
    rec = rec.sort_values("end")
    for m in months:
        known = rec[rec["filed"] <= m]
        if known.empty:
            continue
        last = known.iloc[-1]
        if (m - last["end"]).days > stale_days:
            continue
        out[m] = float(last["adj"])
    return out
