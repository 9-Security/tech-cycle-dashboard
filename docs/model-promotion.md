# Model promotion rule — v2 regime → v3 candidate

**Status:** adopted by the repository owner on 2026-11-23.
**Applies to:** v3 candidate as fixed on its design date, 2026-11-23 (spec fingerprint `c88c89ce…58ef82a`; amended twice the same day, see changelog).
**Live model until promotion:** v2 regime model.

This rule was written *before* any post-design data existed. Changing it after seeing post-design results defeats its purpose; any change must be recorded in the changelog below with its date and reason, and resets the evaluation clock.

## 1. Why a rule is needed

v3 was designed after the full-sample signal study (see [methodology.md](methodology.md) §§ v2.2, 8). Its walk-forward result for 2000–2026 (Sharpe 0.45 vs buy & hold 0.39; P(Sharpe > B&H) 0.74 from a paired bootstrap) is therefore still optimistic. Only months after the design date are a clean test.

## 2. Evaluation window

| Item | Definition |
|---|---|
| First month counted | **2026-12** (the first month whose v3 weight was set after the design date) |
| Returns | v3 walk-forward OOS monthly returns, lag-1, 15 bps costs — the same series shown on the dashboard |
| Benchmark | Buy & hold of the risk asset, and **vol-matched buy & hold**: constant risk fraction = v3 vol / B&H vol over the same window, rest in T-bills (ex-post) |
| Sharpe | Monthly excess return over T-bills, annualised (× √12) |

Note: scaling buy & hold with cash does not change its excess-return Sharpe, so C2 is in effect "v3 Sharpe > buy & hold Sharpe"; the vol-matched series matters for drawdown (C3).

## 3. Criteria — all must hold

| # | Criterion | Threshold |
|---|---|---|
| C1 | Post-design months | **≥ 24** (earliest decision after **2028-11**) |
| C2 | v3 Sharpe vs vol-matched B&H Sharpe, post-design window | v3 **strictly higher** |
| C3 | v3 Max drawdown vs vol-matched B&H, post-design window | no worse than **5 percentage points** below the benchmark |
| C4 | Full OOS history (2000→latest), recomputed with new data | v3 Sharpe ≥ B&H Sharpe |
| C5 | v3 specification unchanged (config values + `model_tilt.py`, `features.py`, `fundamentals.py`, `backtest.py`) | fingerprint equals the frozen value |
| C6 | Operations: longest gap between successful daily refreshes during the window | **≤ 7 days** |

Annual walk-forward refits are part of the v3 specification and do not count as changes.

## 4. Outcomes

| State | Condition | Action |
|---|---|---|
| `collecting` | C1 not yet met | Keep running both models. No decision. |
| `eligible` | C1–C6 all pass | Owner **may** promote v3 (§ 5). Not automatic. |
| `not_met` | C1 met, another criterion fails, fewer than 36 months | Keep collecting; re-check monthly. |
| `retire` | Still not met at **36 months** (after 2029-11) | Retire the v3 candidate, or re-design it with a new design date and fingerprint (clock restarts at 0). |
| `invalid` | C5 fails | The spec changed: set a new design date and fingerprint; the clock restarts at 0. |

## 5. Promotion procedure (owner action)

1. Confirm the state is `eligible` on the Validation page (`data/validation.json → candidate.promotion`).
2. Record the decision in the changelog below (date, post-design months, C2/C3 values).
3. Switch the live posture to v3 in a reviewed pull request.
4. Keep v2 running as a shadow model for 12 months after the switch.

## 6. Limits of this rule

* 24 monthly observations have low statistical power: the rule is a minimum sanity gate, not proof of skill. The post-window paired Sharpe-difference test (v3 vs B&H) is reported for context only.
* Results over 24–36 months depend heavily on which market regime occurs; a single crash or melt-up can decide the outcome.
* The rule judges risk-adjusted performance; it does not consider taxes, trading frictions beyond 15 bps, or product implementation.

## 7. Where it is enforced

| What | Where |
|---|---|
| Thresholds | `engine/tcd/config.py → PromotionRule` |
| Daily status | `engine/tcd/promotion.py`; output in `data/validation.json → candidate.promotion`, shown on `validation.html` |
| Spec-change guard | `engine/tests/test_promotion.py::test_frozen_fingerprint_matches_current_spec` fails CI if v3 code/config changes without a new design date |

## Related evidence (does not change the rule)

* 2026-11-23: pre-registered out-of-domain test of the frozen v3 design on nine other markets **failed** (1/9 markets ahead on Sharpe; mean difference −0.067, 90% CI [−0.158, −0.005]). See [methodology.md](methodology.md) § 11. The criteria above are unchanged; this result should weigh against promotion.

## Changelog

| Date | Change | By |
|---|---|---|
| 2026-11-23 | Rule adopted; design date 2026-11-23; fingerprint `88e42dfdbee76632762785a306dab4136ce7ebdacf2aa8fd9941c8c23faab61d` | owner |
| 2026-11-23 | **Bug-fix amendment, before any post-design month.** An independent code review found a point-in-time defect in `fundamentals.py` (later SEC filings could replace values already known; methodology § 16). Fixing it changes the frozen spec. Per C5 the design date is reset — to the same day, 2026-11-23, so the first counted month stays 2026-12. New fingerprint `6855f9240e3b3bc80c605c2e387a71050cc7d5d8f2868bdf4e448941c4fdb98e`. Effect on the pre-design backtest: v3 OOS Sharpe 0.458 → 0.447. The PSR row is replaced by a paired Sharpe-difference test (0.64 → 0.74). Thresholds unchanged. | owner (approved PR-A) |
| 2026-11-23 | **Second bug-fix amendment, same day, still before any post-design month.** Code-review round 4 fixed the Sortino ratio (standard downside deviation over all months, `backtest.py`) and the partial-month flag on month-ends that are NYSE holidays (`features.py`). Neither changes any v3 weight or the backtest Sharpe (0.447); both files are inside the fingerprint, so per C5 the design date is reset to the same day. New fingerprint `c88c89ce7609e47a04a122edf509aa3e798214cd79aeab2a32cdf059d58ef82a`. | owner (approved PR-D) |
