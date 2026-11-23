"""Pre-registered interim looks for "too many VaR breaches" (methodology section 20).

Registered 2026-11-23, before any live outcome existed. Re-testing a growing
sample every day inflates false alarms, so verdicts are taken only at fixed
looks with a split error budget:

    look (scored days / dates):   60     120    250
    one-sided alpha:              1%     1.5%   2.5%   (total 5%)

Single series (market VaR, challenger): exact binomial test on the breaches of
the FIRST n scored days -> critical counts 8 / 13 / 21 at a 5% target.
Pooled (stock ledger per market, multi-market VaR panel): the null-centred,
date-summed Newey-West z-test (ledger._too_many_test) on the first n dates.

Simulated overall false-alarm rate: single series 2.4% (independent breaches),
5.0% (mild clustering), 8.6% (strong clustering, which Christoffersen flags);
pooled 1.1-5.0% across co-movement / persistence settings. Power of the single
series: true rate 10% -> 24% by day 60, 84% by day 250; 12% -> 43% / 97%.
An early warning, once raised at a look, stays raised (it is a statement about
the first n days).
"""
from __future__ import annotations

from math import comb

import numpy as np

LOOKS = (60, 120, 250)
ALPHAS = (0.01, 0.015, 0.025)
P0 = 0.05


def binom_critical(n: int, alpha: float, p: float = P0) -> int:
    """Smallest c with P(X >= c) <= alpha for X ~ Binomial(n, p)."""
    tail = 0.0
    for c in range(n, -1, -1):
        tail += comb(n, c) * p ** c * (1 - p) ** (n - c)
        if tail > alpha:
            return c + 1
    return 0


def single_series(breaches: np.ndarray) -> dict:
    """breaches: bool array in chronological order (scored days only)."""
    b = np.asarray(breaches, bool)
    looks = []
    for n, a in zip(LOOKS, ALPHAS):
        c = binom_critical(n, a)
        if len(b) < n:
            looks.append({"n": n, "alpha": a, "critical": c, "reached": False})
            continue
        k = int(b[:n].sum())
        looks.append({"n": n, "alpha": a, "critical": c, "reached": True, "breaches": k, "warning": k >= c})
    return _summary(looks)


def pooled(x: np.ndarray, dates: np.ndarray) -> dict:
    """x: breach indicators (0/1) of all names; dates: their target dates."""
    from .ledger import _too_many_test
    x, dates = np.asarray(x, float), np.asarray(dates)
    uniq = np.array(sorted(set(dates.tolist())))
    looks = []
    for n, a in zip(LOOKS, ALPHAS):
        if len(uniq) < n:
            looks.append({"n": n, "alpha": a, "reached": False})
            continue
        m = np.isin(dates, uniq[:n])
        z, p = _too_many_test(x[m], dates[m], P0)
        looks.append({"n": n, "alpha": a, "reached": True, "rate": float(x[m].mean()), "z": z, "p": p,
                      "warning": bool(p < a)})
    return _summary(looks)


def _summary(looks: list[dict]) -> dict:
    reached = [l for l in looks if l["reached"]]
    warned = [l for l in reached if l.get("warning")]
    if warned:
        verdict = f"too_many_at_{warned[0]['n']}"
    elif not reached:
        verdict = "before_first_look"
    elif len(reached) == len(looks):
        verdict = "not_rejected_final"
    else:
        verdict = f"not_rejected_at_{reached[-1]['n']}"
    nxt = next((l["n"] for l in looks if not l["reached"]), None)
    return {"looks": looks, "verdict": verdict, "next_look": nxt}
