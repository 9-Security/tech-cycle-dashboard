# Methodology — engine v3.1 (live, point-in-time, nested walk-forward)

Engine source: [`engine/tcd/`](../engine/tcd). Rebuilt from the v1 specification in this folder; v1 documents are kept for history.

## 1. Question

Can a regime rule built on the **tech Capex cycle** (valuation extension, Capex intensity, earnings momentum, volatility shocks) reduce drawdowns in a tech-equity book **without hindsight**?

## 2. Data (all public, fetched daily)

| Signal / leg | Source | History | Point-in-time rule |
|---|---|---|---|
| Risk asset | Yahoo `XLK` adjusted close; `^NDX` before 1998-12 | 1985→ | month-end close |
| Cash leg | FRED `DTB3` | 1954→ | yield at previous month-end earns this month |
| VIX | Yahoo `^VIX` (FRED `VIXCLS` fills gaps / fallback) | 1990→ | monthly **mean** (configurable) |
| **Valuation (firm)** | Aggregate trailing P/E of the 10 names: Σ market cap / Σ TTM net income, log, rolling 120m z-score | mid-2013→ | price at month-end × share count known at month-end |
| Valuation (proxy) | `^NDX` close / 252-day MA − 1, rolling 120m z-score | 1991→ | daily → month-end |
| Capex intensity (firm) | SEC XBRL companyfacts, 10 names: TTM Capex / TTM revenue | ~2011→ | first-reported value, available on `filed` date |
| Capex intensity (macro proxy) | FRED `A679RC1Q027SBEA` / `GDP` | 1947→ | quarter end + 90 days |
| Earnings momentum (firm) | SEC XBRL TTM net income, 3m growth / rolling std | ~2011→ | same as Capex |
| Earnings momentum (macro proxy) | FRED `CP` (corporate profits) | 1947→ | quarter end + 90 days |

**SEC point-in-time construction** (`fundamentals.py`):
1. For each reporting period keep the **first-reported** value and its filing date; restatements are ignored.
2. Quarterly values come from 3-month facts, or from year-to-date differences (H1 − Q1, 9M − H1, FY − 9M); a derived quarter is available on the later filing date.
3. At each month-end a company's TTM uses only quarters filed by then; quarters must be consecutive and not older than 200 days.
4. Cross-company aggregates are **chain-linked** over names valid in consecutive months, so a name entering the sample causes no jump.

**Aggregate P/E** (`fundamentals.monthly_shares`, `features.py`):
1. Shares: `WeightedAverageNumberOfSharesOutstandingBasic`, else `CommonStockSharesOutstanding` (Alphabet before 2022, all classes combined); first-reported, available on filing date, stale after 200 days.
2. Yahoo `close` is retroactively split-adjusted, so each share count is multiplied by the splits **after its filing date** (a filing already reflects earlier splits under ASC 260). Tested across NVDA's 2021/2024 and AAPL's 2020 splits; per-name market caps match public figures (e.g. AAPL ≈ $2.30T, NVDA ≈ $322B at 2020-12).
3. Names with negative TTM earnings drop out for that month; the ratio is chain-linked like Capex.

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

### v2.1 — aggregate P/E (2026-11-23)

| Valuation input | OOS Sharpe | OOS Max DD | IC vs next-12m return (2013-06 → 2026-10) |
|---|---:|---:|---:|
| Aggregate P/E (default) | 0.11 | −71.9% | **−0.26** |
| Price extension (v2.0) | 0.11 | −71.9% | −0.15 |

P/E is the better valuation signal (stronger negative relation with forward returns; IC on overlapping windows is descriptive only), but strategy results barely move because:
1. Walk-forward keeps choosing overheat thresholds of 1.5–2.0: training data is mostly the pre-2013 proxy era, where defending in "overheat" was costly.
2. Shock (VIX > ~18, ~40% of months) has priority and masks Overheat.

So the binding constraint is the rule structure, not the valuation input. Changing the rules to make the P/E "work" would be fitting the answer; the next research step is to test the Overheat signal on its own (forward returns by signal bucket), separately from the regime machinery.

Live regime effect: at 2026-10-31 the P/E-based valuation z is −1.27 (P/E 18.4×, falling as earnings catch up with Capex), so the official regime moved from Overheat (price proxy) to **Normal**.

These numbers update daily; see the Validation page for the current values.

### v2.2 — stand-alone signal tests (2026-11-23)

Module `engine/tcd/signal_study.py`, page `signals.html`, data `data/signals.json` (recomputed daily). Each signal is tested on its own, outside the regime rules, against (a) the next 1/3/6/12-month excess log return of the risk asset and (b) the probability of a >20% drawdown within 12 months. Quintiles are point-in-time (expanding history, ≥60 months); t-stats are Newey-West (lag h−1); top-minus-bottom spreads carry 12-month moving-block bootstrap 90% CIs. Window 1993-01 → 2025-10 (last month with a full 12-month forward window).

| Signal (de-risk side) | Q5−Q1 next-12m return | Q5−Q1 P(DD > 20%) | 12m IC 1993–2012 | 12m IC 2013+ |
|---|---|---|---:|---:|
| Overheat score (high) | **+19.8 pp** [+0.3, +38.0] | **−31 pp** [−59, −2] | +0.28 | +0.05 |
| Valuation z (high) | +23.7 pp [−6, +44] | −54 pp [−78, −21] | +0.15 | **−0.27** (t −2.1) |
| Capex z (high) | **+16.1 pp** [+8, +24] | −13 pp [−28, 0] | +0.28 | +0.28 (t 2.2) |
| Earnings momentum (low) | +11.0 pp [−3, +26] | −27 pp [−46, −7] → low side had more drawdowns | +0.20 | −0.27 |
| VIX (high) | +3.2 pp [−10, +16] | **+22 pp** [+8, +38] | +0.12 | +0.23 |

Findings:
1. **The Overheat score does not behave like an overheat warning.** High readings preceded *higher* returns and *fewer* large drawdowns; the CI for the return spread excludes zero. In this sample it acts as a pro-cyclical expansion / momentum signal. This explains why walk-forward keeps pushing its threshold up: defending on it sells strength.
2. **Its two components point in opposite directions after 2013.** Firm-level P/E is contrarian as hypothesised (IC −0.27, t −2.1), but Capex intensity is pro-cyclical (IC +0.28, t 2.2 — dominated by the 2023–2025 AI build-out, when Capex and prices rose together). Averaging them cancels (composite IC +0.05). Before 2013 the "valuation" input was price extension, i.e. momentum, so it too was pro-cyclical.
3. **VIX predicts risk, not return.** High VIX does not precede lower average returns, but it precedes more frequent large drawdowns (volatility clustering). This is consistent with the ablation result that Shock-only cuts Max DD to −37%.
4. **Low earnings momentum preceded more drawdowns** (supports the Digestion rule's direction), but the return effect is inconclusive and the sign flips across eras.
5. Extreme tail: the few months with overheat > 2.5 include the 2000 peak (next-12m returns −60% to −95%), but 32 months above 2.0 are too few to separate signal from one episode.

Implications (not implemented — they would be design changes that need their own walk-forward test, not tuning on these results):
* Treat valuation (P/E) and Capex intensity as separate signals with their own signs rather than one averaged score.
* Use VIX as a risk-sizing input (volatility targeting) rather than a binary regime.
* Any redesign chosen *because of* this table is informed by the full sample; it must be judged on data after the change, or with the redesign itself inside the walk-forward loop.

## 6. Known limitations

* **Survivorship**: the 10-name universe is today's leaders.
* **Valuation before mid-2013** is still the price-extension proxy (no XBRL); the dot-com OOS result cannot benefit from P/E.
* P/E uses trailing GAAP earnings (no forward consensus); loss-making names are excluded rather than netted.
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


## 8. v3 candidate — continuous tilts + volatility targeting (designed 2026-11-23)

Module `engine/tcd/model_tilt.py`. Runs daily next to v2; **v2 remains the live posture**.

```
base_w = clip(base + c_px * px_z + c_pe * pe_z + c_capex * capex_z, 0, 1)
base_w *= earn_cut              if earnings score < -1
scale  = min(1, vol_target / sigma_hat)    sigma_hat: 21d / 63d realized tech vol, or VIX x trailing median(realized/VIX)
weight = clip(base_w * scale, 0, 1), 5-pt no-trade band, lag-1, 15 bps
```

Design rules fixed *before* the v3 walk-forward was run:
* Signs are **learned**, not imposed: each coefficient ∈ {0, −0.25, +0.25}; the grid lists 0 first so ties (e.g. P/E before it exists) resolve to the simplest model.
* Price extension and P/E are **separate variables** (the v2 spliced `val_z` changes meaning in 2013). An initial v3 run with a single shared coefficient applied a momentum-learned sign to P/E (cutting exposure because P/E was *low*); that was a specification error and was corrected before any further evaluation. No other iteration was made on OOS results.
* No leverage (weight ≤ 1). Grid: 1,080 configurations.

### Results (OOS 2000-01 → 2026-10)

| Model | Sharpe | CAGR | Vol | Max DD | Final NAV |
|---|---:|---:|---:|---:|---:|
| v2 regime (live) | 0.11 | 2.5% | 14.4% | −71.9% | 1.95 |
| **v3 candidate** | **0.46** | 8.1% | 15.2% | **−56.6%** | 7.99 |
| Buy & hold | 0.39 | 8.5% | 23.0% | −80.5% | 8.98 |
| Vol-matched B&H (to v3, ex-post) | 0.39 | 6.9% | 15.2% | −62.8% | 5.98 |

* v3 beats vol-matched buy & hold by ~0.07 Sharpe and ~6 pts of Max DD; PSR vs B&H Sharpe = 0.64 — **not statistically convincing**.
* Ablation: the price-extension (momentum) tilt carries most of the value (removing it: 0.38); vol targeting adds ~0.05; the Capex tilt *hurts* (removing it: 0.53); P/E adds ~0.03.
* Walk-forward chose c_px = +0.25 (momentum) from 2002 and c_pe = **+0.25** from 2015 — learned from only 2013–2014 P/E data, and opposite to the 12-month contrarian relation in the signal study. Treat the P/E coefficient as unreliable until more P/E history enters training.
* Dot-com: v3 −52% (Max DD −57%) vs B&H −72.5% (−80.5%). 2000 was traded with parameters trained on 1993–1999 (no vol target), so most of the crash was not avoided.
* Sensitivity (vol target × c_pe) is a smooth plateau, not an isolated peak.

### Evaluation protocol from here
* v3's design was informed by full-sample studies, so the table above is still optimistic. Months after **2026-11-23** are the only clean test; they are tracked in `validation.json → candidate.since_design` and `data/history.csv` (`v3_weight`).
* Promotion is governed by the pre-registered rule in [model-promotion.md](model-promotion.md) (adopted 2026-11-23): ≥ 24 post-design months, v3 Sharpe above vol-matched buy & hold, Max DD within 5 pts, unchanged spec, reliable daily refresh. Status is computed daily; the switch is an owner decision.


## 9. Risk estimation — what is and is not predictable (2026-11-23)

Module `engine/tcd/risk_model.py`, page `risk.html`, data `data/risk.json`.

### 9.1 Drawdown-event probability (calibrated logistic model)
* Targets: P(max drawdown of the risk asset worse than −20% within 12 months) and P(worse than −10% within 6 months), month-end closes.
* Inputs at month-end t: log 63d realized vol, log VIX, earnings momentum score, price-extension z. L2 logistic (λ = 1), standardized.
* Walk-forward, refit every January. **Label rule:** the model for year Y is fitted only on rows whose full forward window ended by December Y−1 (tested).
* Baselines: expanding historical base rate (climatology) and a vol-only model. Scores: Brier, Brier skill score (BSS) with 12-month block-bootstrap CI, log loss, AUC, reliability table.

| Target | Model | Event months | BSS vs base rate | 90% CI | AUC |
|---|---|---:|---:|---|---:|
| 12m, −20% | full | 60 / 310 | −0.19 | [−0.46, −0.01] | 0.31 |
| 12m, −20% | vol only | 60 / 310 | −0.14 | [−0.33, +0.02] | 0.27 |
| 6m, −10% | full | 105 / 316 | −0.08 | [−0.21, +0.07] | 0.48 |
| 6m, −10% | vol only | 105 / 316 | +0.01 | [−0.10, +0.14] | 0.57 |

**The model has no out-of-sample skill over the base rate.** Diagnosis (not a code error: predictions are monotone in vol within every year, correlation 0.97–1.0):
1. The 2000–2002 crash was the first event; the 2000 fold had zero known events and the 2001 fold four, so 24 event months were predicted near 0%.
2. Since 2008 there are only **two** 12-month −20% episodes (2008 H1, 2021 H2–2022). Both began from **calm** markets (21d vol 12–25%). The highest-vol months (late 2008, 2009, 2020) were near bottoms and were followed by recoveries, which the model scored as high risk (predicted 50–100% → observed 0%).
3. Correction to the earlier signal study (§ v2.2): the high-VIX → more-drawdowns spread was driven mainly by the prolonged 2000–2002 bear market and does not survive walk-forward. Volatility is largely coincident with, not ahead of, large drawdowns.

**Display rule (fixed before publishing):** if the full model's BSS is not positive with a CI above zero, the dashboard headline shows the historical base rate and labels the model value "reference only".

### 9.2 Next-month volatility forecast
* Target: next month's 21-day realized vol; inputs log rv21 and log VIX at t; OLS refit each January.
* Out-of-sample 2000-01 → 2026-09: **R² 0.50 vs the historical mean, +0.12 vs persistence**, correlation 0.69.

### 9.3 Answer to "can this project estimate risk?"
* **Yes, for risk size:** next-month volatility is forecastable (volatility clustering). That supports volatility targeting (v3) and position sizing.
* **No, for crash events or cycle tops:** with 2–3 episodes, a 12-month drawdown probability model does not beat the base rate; neither did the Overheat signal (§ v2.2). The honest point estimate for "a >20% drawdown within 12 months" is the base rate (~16%).
