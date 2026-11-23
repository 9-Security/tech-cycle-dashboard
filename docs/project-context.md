# Tech cycle backtest — project context

Adapted from the Project store doc of the same name. Source also includes the architecture evolution write-up and the original `tech_cycle_backtest` package (2026-11-21).

## Goal

Institution-grade backtest / risk framework for a tech Capex cycle strategy, mapped to Dot-com (2000) vs AI Capex boom (2026): Capex intensity, shorter GPU depreciation (2–3y), valuation concentration, external shocks.

## Four regimes

1. **Overheat** — high valuation + Capex; defensive tilt  
2. **Shock** — VIX / event flag; max defense / cash  
3. **Digestion** — Capex digest, EPS revisions down; neutral / base-building  
4. **Normal** — fair Capex & valuation; full risk-on  

Priority: Shock → Overheat (score > threshold) → Digestion (EPS revision) → Normal.  
Overheat score = (Valuation Z + Capex Z) / 2. Filing lag enforced to avoid look-ahead. Turnover costs (e.g. 15 bps one-way).

## Pipeline evolution

1. Core backtest + Monte Carlo sensitivity (`regime_engine`, `monte_carlo_sensitivity`)  
2. Block Bootstrap + warm-up + scenario injection (`bootstrap_path_sim`)  
3. Unified runner + Walk-Forward IS/OOS (`experiment_runner`, `walk_forward`)  
4. Data quality gates + proxies (`data_quality`)  
5. Interactive defense simulator + zip packaging  
6. Real public panel + SEC `filing_date` + live refresh / status API + static dashboard (this repo)

## Package layout (`tech_cycle_backtest/`)

- `src/`: `config`, `data_loader`, `data_quality`, `regime_engine`, `backtest`  
- Scripts: `run_prototype`, `monte_carlo_sensitivity`, `bootstrap_path_sim`, `walk_forward`, `experiment_runner`, `fetch_public_panel`, `tune_defenses`, `refresh_live`  
- Sample: `data/raw/events_shock.csv` (+ full public panel in the fixed package)

## Production follow-ups

- Real filing dates + VIX + Forward EPS (Bloomberg / FactSet) — **filing dates wired via SEC `filed`** (see [real-data-wiring.md](real-data-wiring.md)); consensus EPS still proxy  
- Rolling threshold calibration; YoY / FCF proxies when EPS missing  
- Experiment tracking (Git hash / MLflow)  
- Watch OOS Sharpe degradation > ~35%; dynamic ADV-based slippage  

## Related

- Latest metrics: [backtest-run-report-filing-dates.md](backtest-run-report-filing-dates.md)  
- Package how-to: [package-readme.md](package-readme.md)  
