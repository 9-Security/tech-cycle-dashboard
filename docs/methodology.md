# Methodology — engine v2 (live, point-in-time, nested walk-forward)

Engine source: [`engine/tcd/`](../engine/tcd). Rebuilt from the v1 specification in this folder; v1 documents are kept for history.

## 1. Question

Can a regime rule built on the **tech Capex cycle** (valuation extension, Capex intensity, earnings momentum, volatility shocks) reduce drawdowns in a tech-equity book **without hindsight**?

## 2. Data (all public, fetched daily)

| Signal / leg | Source | History | Point-in-time rule |
|---|---|---|---|
| Risk asset | Yahoo `XLK` adjusted close; `^NDX` before 1998-12 | 1985→ | month-end close |
| Cash leg | FRED `DTB3` | 1954→ | yield at previous month-end earns this month |
| VIX | Yahoo `^VIX` (FRED `VIXCLS` fills gaps / fallback) | 1990→ | monthly **mean** (configurable) |
| Valuation proxy | `^NDX` close / 252-day MA − 1, rolling 120m z-score | 1991→ | daily → month-end |
| Capex intensity (firm) | SEC XBRL companyfacts, 10 names: TTM Capex / TTM revenue | ~2011→ | first-reported value, available on `filed` date |
| Capex intensity (macro proxy) | FRED `A679RC1Q027SBEA` / `GDP` | 1947→ | quarter end + 90 days |
| Earnings momentum (firm) | SEC XBRL TTM net income, 3m growth / rolling std | ~2011→ | same as Capex |
| Earnings momentum (macro proxy) | FRED `CP` (corporate profits) | 1947→ | quarter end + 90 days |

**SEC point-in-time construction** (`fundamentals.py`):
1. For each reporting period keep the **first-reported** value and its filing date; restatements are ignored.
2. Quarterly values come from 3-month facts, or from year-to-date differences (H1 − Q1, 9M − H1, FY − 9M); a derived quarter is available on the later filing date.
3. At each month-end a company's TTM uses only quarters filed by then; quarters must be consecutive and not older than 200 days.
4. Cross-company aggregates are **chain-linked** over names valid in consecutive months, so a name entering the sample causes no jump.

**Splicing**: firm-level z-scores replace the macro proxies once they are first valid (~2012–2013). The `capex_src` / `earn_src` columns in `data/panel_monthly.csv` record which source drove each month.

**Not used**: hand-labelled event flags (e.g. "DotCom", "Lehman"). They encode hindsight.

## 3. Regimes and execution

Priority **Shock → Overheat → Digestion → Normal**:

| Regime | Condition | Weight |
|---|---|---|
| Shock | VIX > `vix_threshold` | `w_shock` |
| Overheat | (val_z + capex_z)/2 > `overheat_threshold` | `w_overheat` |
| Digestion | earnings score < `earn_threshold` | `w_digestion` |
| Normal | otherwise | 1.0 |

Lag-1: the weight decided at month-end *t* is held during month *t+1*. Cost: 15 bps per unit of weight change. Remainder sits in T-bills.

## 4. Validation

* **Nested walk-forward (headline)**: each January the 1,440-configuration grid is scored on data from 1993-01 through the previous December only (objective: Sharpe − 2 × drawdown beyond 30%). The winner trades the next 12 months. 2000→today is therefore fully out-of-sample, **including the dot-com crash**.
* **In-sample best** is shown only as a reference: it is the v1 approach (tune on everything, then report).
* **Deflated Sharpe Ratio** for the in-sample best across all 1,440 trials; **PSR** for the OOS track.
* **Ablation**: each variant (no Shock / no Overheat / no Digestion / Shock only) gets its own nested walk-forward.
* **Sensitivity**: full-sample Sharpe over VIX × overheat thresholds.
* **Tests** (`engine/tests/`): future-invariance of the whole panel (truncating data after date D leaves every earlier month unchanged), lag-1 identity, walk-forward choices unaffected by scrambling later returns, XBRL differencing and restatement handling.

## 5. First live result (2026-11-23)

| Track (2000-01 → 2026-10) | Sharpe | Max DD | Final NAV |
|---|---:|---:|---:|
| Walk-forward strategy (OOS) | 0.11 | −71.9% | 1.96 |
| In-sample best, same window | 0.55 | −25.7% | 5.84 |
| Buy & hold | 0.39 | −80.5% | 8.98 |

Findings:
1. The v1 headline (Sharpe ≈ 0.66) is reproduced **in-sample** (0.67 over 1993→2026), but it does not survive walk-forward.
2. Training on 1993–1999 selects an overheat threshold of 2.0 (it never fires): defending during the late-1990s overheat was costly in that window. The strategy therefore did not de-risk before the 2000 crash.
3. Ablation: removing the Shock (VIX) rule *raises* OOS Sharpe to 0.39 ≈ buy & hold; VIX-only keeps Max DD at −37% with Sharpe 0.38. The Overheat / Digestion layers have not shown OOS value yet.
4. In-sample DSR (0.99) looks convincing while OOS fails — a reminder that DSR assumes i.i.d. returns and cannot detect regime-dependent overfitting with only ~2–3 cycles.

These numbers update daily; see the Validation page for the current values.

## 6. Known limitations

* **Survivorship**: the 10-name universe is today's leaders.
* **Valuation** is a price-extension proxy, not P/E. An aggregate mega-cap P/E (price × shares / TTM earnings) is the obvious next step.
* **Macro proxies** use latest-vintage FRED data (revisions are a residual look-ahead; ALFRED vintages would remove it).
* **Pre-1998-12** risk returns are NDX price returns (no dividends).
* Only 2–3 full Capex cycles exist; statistical power is low whatever the method.

## 7. Operations

* `.github/workflows/refresh.yml`: Mon–Fri 22:15 UTC → tests → fetch → DQ gates → walk-forward → commit `data/` → deploy GitHub Pages. Any failure stops before commit/deploy (fail-closed); the site keeps the last good data and its banner turns **stale** after 4 days.
* Partial (in-progress) month: shown as **provisional** regime; never enters the backtest.
* Walk-forward parameters for the live month = the fold for the current year (trained through last December), so live posture and backtest use the same rule.
* Provenance: `data/health.json` holds DQ results, per-source latest dates and a SHA-256 manifest of every raw file; `data/history.csv` logs one row per run day.

```bash
cd engine
pip install -r requirements-dev.txt
python -m pytest -q tests
python -m tcd refresh --out ../data          # online
python -m tcd refresh --offline --out ../data # reuse engine/.cache/raw
```
