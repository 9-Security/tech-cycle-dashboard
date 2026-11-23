"""Future-invariance check on REAL cached data (manual; CI has no raw cache).

Rebuilds the monthly panel with the data truncated at many cutoffs and checks
that every complete month up to each cutoff is identical to the full-sample
panel. Any difference means a later observation changed history (look-ahead).

Usage (from engine/, after an online refresh has filled .cache/raw):
    python tools/check_pit.py [--cache .cache/raw] [--every 2ME] [--start 2008-01-15]
Exit code 1 if any cutoff differs.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from conftest import truncate  # noqa: E402
from tcd.config import EngineConfig  # noqa: E402
from tcd.features import build_panel  # noqa: E402
from tcd.fetch import fetch_all  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", default=".cache/raw")
    ap.add_argument("--every", default="2ME")
    ap.add_argument("--start", default="2008-01-15")
    args = ap.parse_args()
    cfg = EngineConfig()
    raw = fetch_all(Path(args.cache), cfg, offline=True)
    full = build_panel(raw, cfg.features)
    num = [c for c in full.columns if full[c].dtype.kind in "fi"]
    end = full.index[-1] - pd.offsets.MonthEnd(1)
    cuts = pd.date_range(args.start, end, freq=args.every)
    bad = 0
    for cut in cuts:
        p = build_panel(truncate(raw, str(cut.date())), cfg.features)
        comp = p[~p["partial"]]
        a, b = full.loc[comp.index, num], comp[num]
        d = ~np.isclose(a.values, b.values, rtol=1e-9, atol=1e-12, equal_nan=True)
        if d.any():
            bad += 1
            cols = sorted({num[j] for j in np.unique(np.where(d)[1])})
            rows = comp.index[d.any(axis=1)]
            print(f"{cut.date()}: {len(rows)} rows differ ({rows[0].date()} -> {rows[-1].date()}): {cols[:8]}")
    print(f"cutoffs with differences: {bad} of {len(cuts)}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
