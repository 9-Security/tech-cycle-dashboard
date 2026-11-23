# Documentation

Project documentation synced into this repo for the published static dashboard.

**Live app:** https://tech-cycle-dashboard.apps.grok.bot (Private)  
**Current bake:** SEC `filing_date` lag-1 panel · Sharpe **~0.66** · Max DD **−23.80%** · as_of `20261121T035000Z`

## Start here

1. [project-context.md](project-context.md) — what the strategy is and how regimes work  
2. [backtest-run-report-filing-dates.md](backtest-run-report-filing-dates.md) — latest backtest metrics (matches `data/status.json`)  
3. [dashboard-publish.md](dashboard-publish.md) — how this static site was published  

## Backtest & data

| Doc | Topic |
|-----|--------|
| [backtest-run-report-tuned.md](backtest-run-report-tuned.md) | Defense-tuned baseline before filing-date refresh |
| [real-data-wiring.md](real-data-wiring.md) | Public panel sources + `filing_date` contract |
| [package-readme.md](package-readme.md) | Fixed Python package layout and smoke run |

## Dashboard & agents

| Doc | Topic |
|-----|--------|
| [dashboard.md](dashboard.md) | Local Flask UI (charts + scenarios) |
| [live-status-api.md](live-status-api.md) | `refresh_live.py` + `/api/status/latest` |
| [prediction-agent.md](prediction-agent.md) | Forward-looking risk narratives (not trade signals) |

## History

| Doc | Topic |
|-----|--------|
| [code-review.md](code-review.md) | Pre-fix correctness review (look-ahead, Digestion, zip blockers) — issues addressed in the fixed package |

## Provenance

Adapted from the Cursor Project store docs (same filenames under the Project `docs/` folder). Raw CSV experiment dumps and media stay in the store; this folder keeps concise narrative reports only.
