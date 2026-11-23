# Real public data wiring

**Fetcher:** `PYTHONPATH=. python3 fetch_public_panel.py`  
**Date:** 2026-11-23 (filing_date producer update; prior panel 2026-11-21)

## Goal

Replace silent mock fallback with a three-layer public panel that matches `src.data_loader.load_real_monthly_dataset` and the regime engine (`val_pct`, `capex_ratio`, `vix`, `eps_rev_pct`, `shock_flag`, `risk_ret`, `safe_ret`).

Production path uses **`fallback_to_mock=False`**. Missing files raise `FileNotFoundError` with a pointer to the fetcher.

## Ticker / series universe

### Layer 1 — Market returns & valuation

| Role | Source | Series | Notes |
|------|--------|--------|-------|
| Risk basket | Yahoo Finance via `yfinance` | **XLK** | Primary risk close from 1998-12-22 |
| Pre-XLK splice | FRED | **NASDAQ100** | Scaled to XLK on first overlap |
| Valuation input | Derived | `risk_close / 252d MA − 1` | Loader rolls to 0–100 percentile (`val_pct`) over 120m |
| Safe / defensive | FRED | **DTB3** (3M T-bill %) | Monthly `safe_ret` via `tbill_3m_pct` |
| VIX (daily) | FRED | **VIXCLS** | Merged onto trading calendar with ffill |

### Layer 2 — Cycle fundamentals (Capex / EPS)

| Role | Source | Universe | Notes |
|------|--------|----------|-------|
| Capex | SEC EDGAR `companyfacts` | AAPL, MSFT, AMZN, GOOGL, META, NVDA, ORCL, AMD, INTC, AVGO | Prefer `PaymentsToAcquirePropertyPlantAndEquipment` |
| Revenue | SEC EDGAR | same | Prefer `RevenueFromContractWithCustomerExcludingAssessedTax` |
| Pre-XBRL Capex intensity | FRED | **A679RC1Q027SBEA / GDP** | IT equipment ÷ GDP; through first SEC quarter |
| EPS revision proxy | SEC EDGAR | same names | Basic EPS → YoY growth → ΔYoY / 5, clipped ±12% |

**`filing_date` (SEC):** from companyfacts `filed`. Per name/period: earliest original `10-Q`/`10-K` filed date (latest observation supplies restated value). Per calendar-quarter aggregate: max among timely filers (`0–120d` after `period_end`, ≥2 names); else median.

### Layer 3 — Shock

| Role | Source | Notes |
|------|--------|-------|
| Continuous shock | FRED **VIXCLS** | Regime engine uses tuned VIX threshold (~20) |
| Discrete flags | `data/raw/events_shock.csv` | DotCom / Lehman / AI_2026 + COVID_Liquidity_Shock 2020-03-16 |

## Lag / no look-ahead rules

1. **Quarterly fundamentals:** prefer `filing_date`; else `period_end + filing_lag_days` (45), then `merge_asof` backward onto month-ends.
2. **EPS revision:** same availability rule when `period_end` [+ optional `filing_date`] is supplied; legacy `date`-only CSVs = already available.
3. **Market / VIX / T-bill:** point-in-time; monthly uses month-end last / ffill only.
4. **Valuation percentile:** rolling window ending at each month.

## Producer contract (loader)

| File | Required | Optional | Availability |
|------|----------|----------|--------------|
| `tech_fundamentals_quarterly.csv` | `period_end`, `capex`, `revenue` | `filing_date`, `da` | **`filing_date` if present else `period_end + lag`** |
| `eps_revision_monthly.csv` | `eps_rev_pct` + (`period_end` **or** legacy `date`) | `filing_date` | Preferred: `period_end, filing_date, eps_rev_pct` |
| `market_daily.csv` | `date`, `risk_close`\|`close` | `valuation_metric`, `vix_close`, `tbill_3m_pct` | Point-in-time |
| `events_shock.csv` | `date` | `event`, `active` | Event month (+ persistence) |

## Date range

| Artifact | Range |
|----------|-------|
| Config backtest | 1998-01-31 → 2026-10-31 (346 months) |
| SEC Capex/Rev aggregate | 2017-03 → 2026-09 (34 calendar quarters, all with `filing_date`) |
| Pre-XBRL Capex proxy | 1995-Q1 → pre-SEC (`filing_date` blank → +45d lag) |
| EPS revision observations | 69 with `period_end`+`filing_date` |

## Known proxies / limitations

- **XLK + NASDAQ100** is a sector ETF / index proxy, not a custom equal-weight mega-cap book.
- **Safe leg** is cash (T-bill), not TLT/SHY duration.
- **Capex before ~2017** is macro IT-investment intensity, not firm-level hyperscaler Capex.
- **EPS “revision”** is a YoY-growth change proxy (no Bloomberg/FactSet consensus).
- Early XBRL quarters may lack ≥2 timely filers → aggregate `filing_date` falls back to median.

## Refresh

```bash
pip3 install --user yfinance requests scipy pandas numpy tabulate
PYTHONPATH=. python3 fetch_public_panel.py   # fails loud on fetch errors
PYTHONPATH=. python3 run_prototype.py        # fallback_to_mock=False
PYTHONPATH=. python3 experiment_runner.py
```
