# Tech Cycle Dashboard

Live research dashboard for a **tech Capex-cycle regime strategy** (Shock → Overheat → Digestion → Normal, lag-1), rebuilt as a point-in-time engine with **nested walk-forward** validation. Data refreshes every US trading day via GitHub Actions and deploys to GitHub Pages.

> Research only. Not investment advice. Not an auto-trading signal.

## Pages

| Page | Content |
|------|---------|
| [`index.html`](index.html) | Official regime + weight in force, month-to-date provisional regime, OOS metrics, NAV (OOS vs B&H vs in-sample), regime timeline, signals, Capex intensity |
| [`validation.html`](validation.html) | OOS vs hindsight, DSR/PSR, ablation, crisis sub-periods, sensitivity heatmap, per-year fold parameters, DQ + data provenance |
| [`signals.html`](signals.html) | Stand-alone tests of each signal: quintile returns / drawdown odds, Newey-West IC, era stability, threshold events |
| [`scenarios.html`](scenarios.html) | Rule-based trigger distances and scenario cards from live parameters |

## Layout

```
engine/                 Python engine (numpy, pandas, requests)
  tcd/sources/          Yahoo / FRED / SEC fetchers + hashed raw store
  tcd/fundamentals.py   SEC XBRL point-in-time quarterly + TTM + chain-linking
  tcd/features.py       monthly PIT panel (partial month flagged)
  tcd/regime.py         regime rules
  tcd/backtest.py       lag-1 simulation + metrics
  tcd/validation.py     nested walk-forward, ablation, sensitivity, DSR/PSR
  tcd/signal_study.py   stand-alone signal tests (PIT quintiles, NW t, block bootstrap)
  tcd/quality.py        fail-closed data-quality gates
  tcd/status.py         live posture + scenarios
  tcd/export.py         dashboard JSON / CSV (atomic swap)
  tests/                look-ahead / lag-1 / XBRL tests (synthetic data, offline)
data/                   generated artifacts (committed by the daily job)
.github/workflows/      refresh.yml (daily refresh + Pages), ci.yml (tests)
docs/methodology.md     method, results, limitations
```

## Run locally

```bash
cd engine
pip install -r requirements-dev.txt
python -m pytest -q tests
python -m tcd refresh --out ../data
```

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

## One-time GitHub setup

1. **Settings → Pages → Source: GitHub Actions**.
2. **Settings → Secrets and variables → Actions → Variables**: add `SEC_USER_AGENT` = `<your app/org name> <contact email>` (SEC fair-access policy; a generic fallback is used if unset).
3. Merge to `main`; trigger **Actions → Daily refresh & deploy → Run workflow** once.

See [docs/methodology.md](docs/methodology.md) for details.
