# Tech Cycle Dashboard

Static, publishable snapshot of the tech Capex-cycle backtest (filing-date lag-1 run) plus Base / Overheat / Shock scenario briefs.

## What this is

- **Backtest** (`index.html`) — Sharpe / Max DD / CAGR / NAV charts, regime timeline, VIX·overheat·weight panel, scenarios preview
- **Scenarios** (`scenarios.html`) — as-of status cards and 3–6 month risk narratives
- Data is **baked JSON** under `data/` (labeled snapshot / sample). Not live-refreshed on Cursor hosting.

## Local preview

```bash
python3 -m http.server 8765 --bind 127.0.0.1
# open http://127.0.0.1:8765/
```

## Data provenance

| File | Source |
|------|--------|
| `data/series.json` | `docs/backtest-outputs/filing_date_run/prototype_backtest.csv` |
| `data/status.json` | Derived from filing-date last row + overall metrics (`as_of` from live snapshot) |
| `data/scenarios.json` | `docs/backtest-outputs/prediction/scenario_brief.json` (status fields refreshed) |
| `data/health.json` | Static liveness stub |

As of: `20261121T035000Z` · `DATA_SOURCE=REAL` · panel_end `2026-10-31` · Sharpe **0.66**.

## Disclaimer

Scenario analysis for risk discussion only. Not investment advice. Not an auto-trading signal.

## Deploy notes

Static site: `index.html` at project root. No secrets. No server-side refresh.
