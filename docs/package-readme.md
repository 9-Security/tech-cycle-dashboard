# Tech cycle backtest — fixed package

How-to for the fixed Python package (separate from this static dashboard repo). Deliverable was packaged as `tech_cycle_backtest_fixed.zip` in the Project store.

**Verified:** 2026-11-21 — fresh unzip → `py_compile` all `.py` OK → `run_prototype.py` smoke **PASSED** (Sharpe 0.62 on fixed-lag panel; later filing-date refresh → Sharpe **0.66**).

## Unzip & install

```bash
unzip tech_cycle_backtest_fixed.zip
cd tech_cycle_backtest
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt`: numpy, pandas, tabulate, scipy, requests, yfinance, flask.

## Contents (top level)

| Path | Role |
|------|------|
| `src/` | `config`, `data_loader`, `data_quality`, `regime_engine`, `backtest` |
| `run_prototype.py` | Baseline backtest (fail-closed, no mock) |
| `experiment_runner.py` | Full pipeline: DQ, MC, bootstrap, Walk-Forward, MD report |
| `fetch_public_panel.py` | Public Yahoo/FRED/SEC fetch → `data/raw/` |
| `tune_defenses.py` | Defense threshold/weight search (lag-1) |
| `refresh_live.py` | Live snapshot refresh (see [live-status-api.md](live-status-api.md)) |
| `dashboard/` | Flask UI |
| `data/raw/` | Sample real panel |
| `data/outputs/` | Sample run artifacts |

## Fetch data (refresh)

Packaged `data/raw/` is enough to run offline. To refresh from public sources:

```bash
PYTHONPATH=. python3 fetch_public_panel.py
```

Producer contract: [real-data-wiring.md](real-data-wiring.md).

## Run backtest

```bash
PYTHONPATH=. python3 run_prototype.py
PYTHONPATH=. python3 experiment_runner.py
# optional: PYTHONPATH=. python3 tune_defenses.py
```

## Tuned baseline card (frozen)

| Knob | Value |
|------|-------|
| Overheat threshold | 1.3476 |
| VIX shock | 20.027 |
| EPS Digestion (3m) | −0.04922 |
| Weights OH / Shock / Digestion / Normal | 0.5897 / 0.0639 / 0.4848 / 1.00 |
| Cost | **15 bps** one-way |
| Execution | **Lag-1** executed weights |

Smoke (fixed-lag packaged panel): Sharpe **0.62**, Max DD **−23.80%**.  
Filing-date panel (dashboard bake): Sharpe **0.66**, Final NAV **5.033** — see [backtest-run-report-filing-dates.md](backtest-run-report-filing-dates.md).

## What changed vs original zip (summary)

| Area | Fix |
|------|-----|
| Look-ahead | Lag-1 executed weights; WF handoff on exec weight |
| Regimes | Shock = VIX\|flag; Digestion via EPS (doc priority) |
| Mock | Default `fallback_to_mock=False`; stamp `DATA_SOURCE` |
| Filing lag | Prefer `filing_date`; same rule for EPS |
| Costs | 15 bps; t0 turnover = 0 |
| Packaging | Syntax + NameError fixed; scipy in requirements |

Full historical review of the original zip: [code-review.md](code-review.md).
