# Tech cycle backtest — real SEC `filing_date` wiring

**Date:** 2026-11-23  
**Prior tuned report:** [backtest-run-report-tuned.md](backtest-run-report-tuned.md)  
**Config:** tuned `BacktestConfig` baseline (`fallback_to_mock=False`, 15 bps, lag-1)

> This is the **latest** full-sample snapshot baked into this dashboard (`data/status.json`: Sharpe **0.66**).

## What changed

1. **`fetch_public_panel.py`** — Capex/Revenue/EPS aggregates now emit SEC companyfacts **`filed`** as `filing_date`.
   - Per ticker/period: **value** = latest observation; **filing_date** = earliest original `10-Q`/`10-K` `filed` (amendments do not delay availability).
   - Per calendar quarter aggregate: `filing_date` = max among **timely** filers (`0 ≤ filed − period_end ≤ 120d`, need ≥2); else median of all (XBRL backfill guard).
   - Pre-XBRL FRED Capex proxy rows leave `filing_date` blank → loader `period_end + 45d`.
   - EPS CSV schema moved from legacy producer-lagged `date` to **`period_end, filing_date, eps_rev_pct`**.
2. **`data_loader.py`** — already preferred `filing_date` (M2); verified end-to-end for Capex + EPS.
3. Re-fetched panel + `run_prototype.py` + `experiment_runner.py` (both `fallback_to_mock=False`).

## Metrics — tuned vs filing_date

| Metric | Tuned (fixed 45d / legacy EPS date) | **Filing dates** | Δ |
|--------|-------------------------------------|------------------|---|
| Sharpe | 0.62 | **0.66** | **+0.04** |
| Max DD % | −23.80 | **−23.80** | 0 |
| CAGR % | 5.25 | **5.76** | **+0.51** |
| Ann. vol % | 8.97 | 9.09 | +0.12 |
| Period ret % | 336.74 | **403.31** | **+66.6** |
| Final NAV | 4.367 | **5.033** | **+0.666** |
| Ann. turnover | 1.47 | 1.62 | +0.15 |
| Total cost % | 6.38 | 6.99 | +0.61 |
| BH Sharpe / MDD | 0.59 / −80.47 | unchanged | — |

### Regime months

| Regime | Tuned | Filing dates |
|--------|------:|-------------:|
| 1 Overheat | 40 | **45** |
| 2 Shock | 140 | 140 |
| 3 Digestion | 65 | **59** |
| 4 Normal | 101 | **102** |

### Subperiods (filing_date run)

| Period | Strat ret % | Strat Sharpe | Strat MDD % | BH MDD % |
|--------|------------:|-------------:|------------:|---------:|
| DotCom 2000–2002 | −19.93 | −0.92 | −23.66 | −80.47 |
| GFC 2008–2009 | −3.25 | −0.44 | −6.89 | −43.65 |
| AI 2023–2026 | **45.56** | **0.82** | −12.41 | −11.36 |

(Tuned AI ret was 36.93 / Sharpe 0.72 — main lift is later-cycle Capex/EPS timing.)

### Walk-Forward IS→OOS (experiment_runner, rolling)

| Metric | Tuned IS→OOS | Filing-date IS→OOS |
|--------|--------------|--------------------|
| Sharpe | 0.77 → 1.11 (+44.9%) | 0.78 → 1.10 (+40.0%) |
| CAGR % | 8.49 → 9.89 (+16.4%) | 8.49 → 9.72 (+14.5%) |
| Max DD % | −21.53 → −6.93 | −21.39 → −6.81 |

Still OOS > IS on Sharpe (within ≤35% worsening budget).

## Sample `filing_date` vs `period_end` lags

SEC Capex/Rev quarters with non-null `filing_date` (**n=34**): median lag **33d**, mean 80d (early XBRL-sparse quarters pull the mean; from 2018-Q1 onward lags cluster ~28–37d).

EPS observations (**n=69**): lag median **33d**, mean 34.4d, range 26–58d.

Pre-XBRL Capex proxy (1995→first SEC quarter): `filing_date` blank → loader uses `period_end + 45`.

## Exit status

| Step | Status |
|------|--------|
| `fetch_public_panel.py` (SEC+FRED+Yahoo) | **success** — fund `filing_date` non-null=34/34 SEC qtrs; EPS=69/69 |
| `run_prototype.py` | **success** — `DATA_SOURCE=REAL`, DQ PASSED |
| `experiment_runner.py` | **success** |

## Notes / limits

- Early SEC quarters (2017) can still show long lags when &lt;2 names have timely XBRL tags.
- Aggregate `filing_date` is a panel PIT proxy (timely-filer max), not a single-name EDGAR accession timestamp.
- Dashboard bake uses this run’s metrics (final strat NAV **5.033**).

Producer contract: [real-data-wiring.md](real-data-wiring.md).
