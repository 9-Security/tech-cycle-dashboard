# Tech cycle backtest — code review (summary)

**Date:** 2026-11-21  
**Scope:** Original packaged zip vs architecture / project context.  
**Status:** Historical — blockers below were addressed in the **fixed package** and subsequent filing-date work. See [package-readme.md](package-readme.md).

## Verdict (at review time)

Not institution-ready as originally packaged. Core modules showed a coherent skeleton, but three correctness gaps invalidated look-ahead control and documented Capex-cycle regimes until patched.

## Top issues (then) → resolution

| # | Issue | Resolution in fixed package / later |
|---|--------|-------------------------------------|
| **B1** | Same-month regime weight × same-month return (look-ahead) | Lag-1 `exec_w`; turnover on exec series; WF handoff on executed weight |
| **B2** | EPS Digestion folded into Shock | Shock = VIX \| event flag; Digestion via EPS threshold (+ mild hysteresis) |
| **B3** | Unrunnable zip (syntax escapes + report NameError) | Re-escaped strings; fixed kwarg; `py_compile` clean |
| **M1** | Silent mock fallback | Default `fallback_to_mock=False`; stamp `DATA_SOURCE` |
| **M2** | Incomplete filing lag / no `filing_date` | Prefer `filing_date`; EPS same rule — see [real-data-wiring.md](real-data-wiring.md) |
| **M3** | Cost 10 bps vs documented 15 | Set 15 bps; t0 turnover = 0 |
| **M4** | WF “degradation” not true IS→OOS | IS→OOS under selected params |
| **M5–M6** | Bootstrap shocks / valuation Z-of-percentile drift | Documented; scipy required; block shocks preserved |

## Current metrics (post-fix)

After defense tuning + SEC `filing_date` panel: Sharpe **~0.66**, Max DD **−23.80%**. Details: [backtest-run-report-filing-dates.md](backtest-run-report-filing-dates.md).

The full original review (blockers with code excerpts, majors, minors) remains in the Project store as `docs/code-review.md` if needed for audit trail.
