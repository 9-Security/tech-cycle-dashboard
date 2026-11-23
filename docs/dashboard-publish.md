# Tech cycle dashboard — publish status

Static Cursor-hostable dashboard (filing-date lag-1 snapshot + scenarios). **Published and live.**

## Status

| Field | Value |
|-------|--------|
| Status | **Published / live** |
| Slug | `tech-cycle-dashboard` |
| Live URL | https://tech-cycle-dashboard.apps.grok.bot |
| Visibility | **Private** (owner can change in Publish Settings) |
| Repo | https://github.com/9-Security/tech-cycle-dashboard |
| Initial publish PR | https://github.com/9-Security/tech-cycle-dashboard/pull/1 (**merged** into `main`) |

Data is baked snapshot / sample — not live-refreshed; no secrets required for this static app.

## App layout (repo root)

| Path | Role |
|------|------|
| `index.html` / `scenarios.html` | Pages |
| `css/`, `js/`, `static/` | Styles, Chart.js, page scripts |
| `data/*.json` | Baked series, status, scenarios, health |

`publish-app` uses `project_dir: .` (repo root).

## Current bake

| Field | Value |
|-------|--------|
| as_of | `20261121T035000Z` |
| DATA_SOURCE | REAL |
| panel_end | 2026-10-31 |
| Sharpe | **0.66** |
| Max DD | −23.80% |
| CAGR | 5.76% |
| Final NAV | 5.033 |

Provenance detail: root [README.md](../README.md) and [backtest-run-report-filing-dates.md](backtest-run-report-filing-dates.md).

## Republish

Docs-only changes do **not** require republishing the app. Republish after changing baked JSON or front-end assets.
