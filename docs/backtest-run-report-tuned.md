# Tech cycle backtest — tuned defenses (lag-1)

**Date:** 2026-11-21  
**Tuner:** `PYTHONPATH=. python3 tune_defenses.py` (seed `20261121`)  
**Constraints held:** lag-1 execution, `fallback_to_mock=False`, 15 bps, Shock→Overheat→Digestion→Normal

> Superseded for dashboard bake by [backtest-run-report-filing-dates.md](backtest-run-report-filing-dates.md) (Sharpe 0.66). Kept as the frozen defense-parameter baseline.

## Chosen parameters (frozen into `BacktestConfig` / `BASELINE_CARD`)

| Knob | Majors | **Tuned** |
|------|--------|-----------|
| `overheat_threshold` | 1.25 | **1.3476** |
| `vix_shock_threshold` | 25.0 | **20.027** |
| `eps_rev_3m_threshold` | −0.03 | **−0.04922** |
| `weight_overheat` | 0.70 | **0.5897** |
| `weight_shock` | 0.25 | **0.0639** |
| `weight_recovery` | 0.60 | **0.4848** |
| `weight_normal` | 1.00 | 1.00 |
| `transaction_cost_rate` | 0.0015 | 0.0015 |

## Rationale

1. **Phase 1** — 368 full-sample configs (uniform MC + defense-tilted cloud + hand anchors). Composite favored Max-DD cut and Sharpe lift vs majors.
2. **Phase 2** — Fixed-parameter rolling Walk-Forward on top 18 (lag-1 + cross-fold exec-weight handoff). All shortlisted configs showed **positive** IS→OOS Sharpe (OOS > IS); none violated the “no worse than −35%” degradation guard.
3. **Selection** — Ranked by MDD improvement, OOS Sharpe, then full-sample Sharpe. Winner: earlier Shock (VIX≈20), deeper Shock/Overheat/Digestion defense weights, slightly stricter EPS Digestion threshold.
4. **Trade-off** — Full-sample NAV (4.37) is slightly below majors (4.94) because the book spends more time in cash/defense; risk-adjusted metrics and Max DD improve sharply. Dot-com MDD −23.7% vs BH −80.5%.

## Metrics — majors vs tuned

| Metric | Majors | **Tuned** |
|--------|--------|-----------|
| Sharpe | 0.43 | **0.62** |
| Max DD % | −74.59 | **−23.80** |
| CAGR % | 5.70 | **5.25** |
| Ann. vol % | 15.69 | **8.97** |
| Final NAV | 4.943 | **4.367** |
| Total cost % | 5.12 | 6.38 |
| BH Sharpe / MDD | 0.59 / −80.47 | (unchanged) |

### Regime months

| Regime | Majors | Tuned |
|--------|--------|-------|
| 1 Overheat | 49 | **40** |
| 2 Shock | 74 | **140** |
| 3 Digestion | 84 | **65** |
| 4 Normal | 139 | **101** |

### Subperiods (tuned)

| Period | Strat ret % | Strat Sharpe | Strat MDD % | BH MDD % |
|--------|-------------|--------------|-------------|----------|
| DotCom 2000–2002 | −19.93 | −0.92 | **−23.66** | −80.47 |
| GFC 2008–2009 | −3.25 | −0.44 | **−6.89** | −43.65 |
| AI 2023–2026 | 36.93 | 0.72 | −12.41 | −11.36 |

### Walk-Forward IS→OOS (after freeze)

| Metric | IS mean | OOS mean | Degradation |
|--------|---------|----------|-------------|
| Sharpe | 0.77 | **1.11** | **+44.9%** (OOS > IS; within ≤35% *worsening* budget) |
| CAGR % | 8.49 | 9.89 | +16.4% |
| Max DD % | −21.53 | −6.93 | −67.8% magnitude |

Lag check after freeze: `risk_weight[t] == target_weight[t-1]`, t0 turnover = 0.

## Exit status

| Step | Status |
|------|--------|
| `tune_defenses.py` | **success** |
| `run_prototype.py` | **success** — `DATA_SOURCE=REAL` |
| `experiment_runner.py` | **success** |
