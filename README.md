# Tech Cycle Dashboard

Live research dashboard for a **tech Capex-cycle strategy**: the live v2 regime model (Shock → Overheat → Digestion → Normal, lag-1) and a v3 candidate (continuous valuation/Capex tilts + volatility targeting), both validated by **nested walk-forward** on a point-in-time engine. Data refreshes every US trading day via GitHub Actions and deploys to GitHub Pages.

> Research only. Not investment advice. Not an auto-trading signal.

## Pages

All pages are bilingual (English / 繁體中文). Use the switch in the top bar, or open any page with `?lang=zh-TW` / `?lang=en`; the choice is remembered in the browser. Translations live in `js/i18n.js`; narrative sentences (scenarios, verdicts, promotion status) are rebuilt in the browser from structured fields in `data/*.json`, so both languages come from the same numbers.

| Page | Content |
|------|---------|
| [`index.html`](index.html) | Daily risk light (green / yellow / red, plain language, en / zh-TW); Official regime + weight in force, month-to-date provisional regime, OOS metrics, NAV (OOS vs B&H vs in-sample), regime timeline, signals, Capex intensity |
| [`validation.html`](validation.html) | v2 vs v3 model comparison; per model: OOS vs hindsight, DSR/PSR, ablation, crisis sub-periods, sensitivity heatmap, per-year fold parameters, DQ + data provenance |
| [`signals.html`](signals.html) | Stand-alone tests of each signal: quintile returns / drawdown odds, Newey-West IC, era stability, threshold events |
| [`risk.html`](risk.html) | Next-day / 5-day volatility and 1-day 95% VaR (daily HAR + VIX, backtested); next-month volatility forecast (forecastable) and drawdown-event probability with out-of-sample skill vs the base rate (not skillful; base rate shown as headline) |
| [`stocks.html`](stocks.html) | 28 stocks (US mega caps + Taiwan AI supply chain): per-stock risk light, next-day vol, 1-day VaR with backtest badge, beta, drawdown; US SEC fundamentals. Edit `engine/watchlist.json` to change the list |
| [`scenarios.html`](scenarios.html) | Rule-based trigger distances and scenario cards from live parameters |

## Layout

```
engine/                 Python engine (numpy, pandas, requests)
  tcd/sources/          Yahoo / FRED / SEC fetchers + hashed raw store
  tcd/fundamentals.py   SEC XBRL point-in-time quarterly + TTM + chain-linking
  tcd/features.py       monthly PIT panel (partial month flagged)
  tcd/regime.py         v2 regime rules
  tcd/model_tilt.py     v3 tilts + vol targeting
  tcd/backtest.py       lag-1 simulation + metrics
  tcd/validation.py     nested walk-forward, ablation, sensitivity, DSR/PSR
  tcd/signal_study.py   stand-alone signal tests (PIT quintiles, NW t, block bootstrap)
  tcd/risk_model.py     walk-forward drawdown probability (logistic) + volatility forecast
  tcd/short_risk.py     daily HAR volatility + 95% VaR (EWMA baseline, VIX, EPU news test)
  tcd/cross_market.py   pre-registered out-of-domain test of v3 on 9 other markets
  tcd/light.py          daily risk light (codes + numbers; text rendered per language)
  tcd/ledger.py         live stock forecast ledger (append-only) + reconciliation
  tools/validate_data.py pre-commit checks of data/ (strict JSON/CSV, append-only ledger, no e-mail)
  tools/archive_raw.py  archive raw inputs to a private R2 bucket (content-addressed)
  tools/restore_raw.py  rebuild a raw cache from an archive index
  tools/check_pit.py    manual future-invariance check on real cached data (no look-ahead)
  tcd/market_ledger.py  live forecast ledger for the market VaR / volatility (append-only)
  tcd/tw_calendar.py    removes Yahoo bars on Taiwan market holidays before the stock model
  tcd/official_check.py second-source closes: TW vs TWSE / TPEx, US vs Nasdaq (report only)
  tcd/stocks.py         per-stock risk monitoring + US fundamentals (watchlist.json)
  tcd/quality.py        fail-closed data-quality gates
  tcd/status.py         live posture + scenarios
  tcd/export.py         dashboard JSON / CSV (atomic swap)
  tests/                look-ahead / lag-1 / XBRL tests (synthetic data, offline)
data/                   generated artifacts (committed by the daily job)
  forecasts/            append-only stock forecast ledger + scored outcomes
.github/workflows/      refresh.yml (daily refresh + Pages; extra Taiwan-stocks run 07:07 UTC), ci.yml (tests)
docs/methodology.md     method, results, limitations
```

## Run locally

```bash
cd engine
pip install --require-hashes -r requirements-dev.lock
python -m pytest -q tests
python -m tcd refresh --out ../data
```

```bash
python3 -m http.server 8765 --bind 127.0.0.1
```

## One-time GitHub setup

1. **Settings → Pages → Source: GitHub Actions**.
2. **Settings → Secrets and variables → Actions → Secrets**: add `SEC_USER_AGENT` = `<your app/org name> <contact email>` (SEC fair-access policy; a generic fallback is used if unset). Use a **secret**, not a variable: variables are printed unmasked in workflow logs, which are public for a public repository.
3. Merge to `main`; trigger **Actions → Daily refresh & deploy → Run workflow** once.

See [docs/methodology.md](docs/methodology.md) for details.
