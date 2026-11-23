# Tech cycle backtest — dashboard

Two surfaces:

1. **This repo (published)** — static HTML/JS bake at https://tech-cycle-dashboard.apps.grok.bot (Private). See [dashboard-publish.md](dashboard-publish.md).
2. **Local Flask UI** — interactive charts + optional scenario refresh against the Python package.

## Static preview (this repo)

```bash
python3 -m http.server 8765 --bind 127.0.0.1
# open http://127.0.0.1:8765/
```

Pages: [`index.html`](../index.html) (backtest), [`scenarios.html`](../scenarios.html) (briefs).

## Flask UI (package)

```bash
pip3 install --user flask pandas   # if needed
PYTHONPATH=. python3 dashboard/app.py
```

Open:

- **http://127.0.0.1:8765/** — backtest charts + scenarios preview  
- **http://127.0.0.1:8765/scenarios** — Base / Overheat / Shock brief  

Health: `curl -s http://127.0.0.1:8765/api/health`

## What it shows

1. **Metrics cards** — Sharpe, Max DD, CAGR, Final NAV (vs buy & hold)  
2. **NAV chart** — strategy vs buy & hold (log scale)  
3. **Regime timeline** — color strip + stepped regime codes  
4. **Aux panel** — VIX, overheat score, executed risk weight  
5. **Scenarios** — 3–6 month Base / Overheat / Shock narratives  

## APIs (Flask)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness + as_of |
| GET | `/api/series` | Chart series |
| GET | `/api/status/latest` | Live regime / weights |
| GET | `/api/history?limit=N` | Snapshot metadata |
| GET | `/api/scenarios` | Current scenario brief JSON |
| GET | `/api/scenarios?refresh=1` | Regenerate via `predict_scenarios.py` |

## Notes

- Read-only for charts; scenarios refresh is optional and fail-closed on non-REAL status.
- Scenario text is risk narrative only — not investment advice or auto-trading.
- Static bake metrics match [backtest-run-report-filing-dates.md](backtest-run-report-filing-dates.md) (Sharpe ~0.66).
