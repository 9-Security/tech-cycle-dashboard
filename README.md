# Tech Cycle Dashboard

Static, publishable snapshot of an institution-style **tech Capex-cycle backtest** (Dot-com 2000 vs AI Capex boom), plus Base / Overheat / Shock scenario briefs. Charts and status are frozen JSON under `data/` — not live-refreshed on the hosted app.

## Live app

| | |
|---|---|
| **URL** | https://tech-cycle-dashboard.apps.grok.bot |
| **Visibility** | Private (owner can change in Publish Settings) |
| **Mode** | Baked snapshot / sample data |

## Snapshot (current bake)

Lag-1 execution · SEC `filing_date` fundamentals · `DATA_SOURCE=REAL` · panel **1998-01 → 2026-10**.

| Metric | Value |
|--------|------:|
| Sharpe | **~0.66** |
| Max DD | −23.80% |
| CAGR | 5.76% |
| Final NAV | 5.033 |
| as_of | `20261121T035000Z` |

Buy & hold (same panel): Sharpe 0.59 · Max DD −80.47%.

## What this repo is

| Page | Role |
|------|------|
| [`index.html`](index.html) | Sharpe / Max DD / CAGR / NAV charts, regime timeline, VIX·overheat·weight, scenarios preview |
| [`scenarios.html`](scenarios.html) | As-of status cards + 3–6 month risk narratives |
| [`data/`](data/) | Baked `series.json`, `status.json`, `scenarios.json`, `health.json` |

This repo hosts the **dashboard surface**. The Python backtest package (regime engine, fetcher, Flask API, prediction agent) lives separately; see [docs/](docs/).

## Run locally

```bash
# From repo root — any static file server
python3 -m http.server 8765 --bind 127.0.0.1
# open http://127.0.0.1:8765/
```

No build step, no secrets, no server-side refresh.

## Docs

| Doc | Summary |
|-----|---------|
| [docs/README.md](docs/README.md) | Docs index |
| [docs/project-context.md](docs/project-context.md) | Strategy goal, four regimes, pipeline |
| [docs/backtest-run-report-filing-dates.md](docs/backtest-run-report-filing-dates.md) | **Latest metrics** (Sharpe ~0.66) |
| [docs/backtest-run-report-tuned.md](docs/backtest-run-report-tuned.md) | Prior tuned baseline (Sharpe 0.62) |
| [docs/real-data-wiring.md](docs/real-data-wiring.md) | Yahoo / FRED / SEC producer contract |
| [docs/dashboard.md](docs/dashboard.md) | Local Flask UI (dev) |
| [docs/dashboard-publish.md](docs/dashboard-publish.md) | Publish status for this static app |
| [docs/live-status-api.md](docs/live-status-api.md) | Refresh pipeline + status JSON API |
| [docs/prediction-agent.md](docs/prediction-agent.md) | Scenario / forecast agent |
| [docs/package-readme.md](docs/package-readme.md) | Fixed backtest package how-to |
| [docs/code-review.md](docs/code-review.md) | Historical review summary (pre-fix) |

Source of truth for Project working notes remains the Cursor Project store (`docs/` there); copies here are adapted for the GitHub repo (relative links, no store-only CSV dumps).

## Disclaimer

Scenario analysis for risk discussion only. Not investment advice. Not an auto-trading signal.
