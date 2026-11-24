# Methodology — engine v3.5 (live, point-in-time, nested walk-forward)

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
4. In-sample DSR (0.97; reported as 0.99 in the first run) looks convincing while OOS fails — a reminder that DSR assumes i.i.d. returns and cannot detect regime-dependent overfitting with only ~2–3 cycles.

### v2.1 — aggregate P/E (2026-11-23)

| Valuation input | OOS Sharpe | OOS Max DD | IC vs next-12m return (2013-06 → 2026-10) |
|---|---:|---:|---:|
| Aggregate P/E (default) | 0.11 | −71.9% | **−0.26** |
| Price extension (v2.0) | 0.11 | −71.9% | −0.15 |

P/E is the better valuation signal (stronger negative relation with forward returns; IC on overlapping windows is descriptive only), but strategy results barely move because:
1. Walk-forward keeps choosing overheat thresholds of 1.5–2.0: training data is mostly the pre-2013 proxy era, where defending in "overheat" was costly.
2. Shock (VIX > ~18, ~40% of months) has priority and masks Overheat.

So the binding constraint is the rule structure, not the valuation input. Changing the rules to make the P/E "work" would be fitting the answer; the next research step is to test the Overheat signal on its own (forward returns by signal bucket), separately from the regime machinery.

Live regime effect: at 2026-10-31 the P/E-based valuation z is −1.27 (the 18.4× quoted here was the chain-linked P/E index, not a P/E level; the actual Σ market cap ÷ Σ TTM net income was ≈ 25× — see § 16), so the official regime moved from Overheat (price proxy) to **Normal**.

These numbers update daily; see the Validation page for the current values.

### v2.2 — stand-alone signal tests (2026-11-23)

Module `engine/tcd/signal_study.py`, page `signals.html`, data `data/signals.json` (recomputed daily). Each signal is tested on its own, outside the regime rules, against (a) the next 1/3/6/12-month excess log return of the risk asset and (b) the probability of a >20% drawdown within 12 months. Quintiles are point-in-time (expanding history, ≥60 months); t-stats are Hodrick (1992) 1B and top-minus-bottom spreads are tested with a circular-shift test (verdict at p < 0.05); until 2026-11-23 they were Newey-West (lag h−1) t-stats and 12-month block-bootstrap CIs, which simulation showed to give false positives two to four times as often as stated for signals this persistent (§ 16). Window 1993-01 → 2025-10 (last month with a full 12-month forward window).

| Signal (de-risk side) | Q5−Q1 next-12m return (shift-test p) | Q5−Q1 P(DD > 20%) (p) | 12m IC (Hodrick t) 1993–2012 | 12m IC (Hodrick t) 2013+ |
|---|---|---|---:|---:|
| Overheat score (high) | +20.4 pp (0.09) | −30 pp (0.12) | +0.28 (1.1) | +0.07 (0.1) |
| Valuation z (high) | **+23.6 pp (0.01)** | **−53 pp (< 0.01)** | +0.15 (1.0) | −0.23 (−0.9) |
| Capex z (high) | +16.6 pp (0.33) | −13 pp (0.68) | +0.28 (0.6) | +0.28 (1.0) |
| Earnings momentum (low) | +11.7 pp (0.22) | **−27 pp (< 0.01)** → low side had more drawdowns | +0.20 (1.4) | −0.25 (−1.0) |
| VIX (high) | +3.2 pp (0.83) | +22 pp (0.27) | +0.12 (0.7) | +0.23 (1.1) |

Numbers after the 2026-11-23 corrections (§ 16: point-in-time fix of the SEC inputs, Hodrick t-stats, circular-shift test). Under the original, over-confident inference several cells were reported as significant; the corrected readings are:

Findings:
1. **The Overheat score does not behave like an overheat warning.** High readings preceded *higher* returns and *fewer* large drawdowns, but neither difference is significant once the persistence of the signal is accounted for (p 0.09 and 0.12; previously reported as significant). It is at best uninformative for de-risking, never supportive.
2. **High valuation preceded higher returns and fewer drawdowns** (p 0.01 and < 0.01): over 1993–2025 the valuation input (price extension before 2013, P/E after) behaved pro-cyclically. The post-2013 split between a contrarian P/E (t −2.1) and a pro-cyclical Capex (t 2.2) reported earlier does **not** survive Hodrick t-stats (−0.9 and 1.0): it is noise at this sample size.
3. **VIX: the drawdown effect is no longer significant** (p 0.27; previously "supports"). Volatility clustering is still visible at short horizons (§ 10), but not as a 12-month drawdown predictor in this test.
4. **Low earnings momentum preceded more drawdowns** (p < 0.01; supports the Digestion rule's direction); the return effect is inconclusive and the sign flips across eras.
5. Extreme tail: the few months with overheat > 2.5 include the 2000 peak (next-12m returns −60% to −95%), but 32 months above 2.0 are too few to separate signal from one episode.

Implications (not implemented — they would be design changes that need their own walk-forward test, not tuning on these results):
* Treat valuation (P/E) and Capex intensity as separate signals with their own signs rather than one averaged score. (This implication, which shaped v3, rested on the post-2013 t-stats −2.1 / +2.2 that the corrected Hodrick t-stats no longer support (−0.9 / +1.0); see § 16.)
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

* `.github/workflows/refresh.yml`: Mon–Fri 22:15 UTC → tests → fetch → DQ gates → walk-forward → commit `data/` → deploy GitHub Pages. A second run, Mon–Fri 07:07 UTC (15:07 Taiwan time, after the TWSE close), refreshes only the Taiwan stocks of the Stocks page (`python -m tcd stocks --market TW`); manual runs pick `full` or `tw`.
* **Backup schedules (2026-11-24).** GitHub can delay or drop a scheduled run (the first 22:15 UTC run, 2026-11-23, never started). Backups at 23:41 UTC (full) and 08:37 UTC (Taiwan) run only if the data were not already published after that market's close the same day (`health.json → as_of` ≥ 21:00 UTC; `stocks.json → run_issues.TW.as_of` ≥ 06:00 UTC); otherwise a small `gate` job ends the run with no refresh, deploy or notification. A backup re-run is safe by construction: ledgers are first-write-wins, `history.csv` keeps one row per day and alerts fire only on a new close. The weekly look-ahead check also runs on Monday's backup.
* **Failure handling.** The core model is fail-closed: a fetch failure, a failed data-quality gate or a crash stops the run before commit/deploy, the site keeps the last good data and its banner turns **stale** after 4 days. Report-only blocks (cross-market test, stock monitor, second-source check, forecast ledger) never block the core model; since 2026-11-23 their failures are recorded in `health.json → report_issues` (`degraded: true`) and shown in the banner, and a second-source outage keeps the last good comparison (marked `stale`) instead of overwriting it. The Taiwan-only run refuses to write when `^TWII`'s last bar is older than 7 days and writes nothing when there is no new bar (holiday); its issues go to `stocks.json → run_issues`.
* **No publishing during a session.** If the latest daily bar is still being traded (a manual run during the US session for the full refresh, or the Taiwan session for the Taiwan run), the engine writes nothing and exits normally; pass `--allow-intraday` (workflow input `allow_intraday`) to publish anyway. Until 2026-11-23 a manual run during the session published an unfinished day (prices, regime inputs, VaR) until the next run.
* **Weekly look-ahead check.** Monday's full run (or a manual run with `pit_check`) re-runs `engine/tools/check_pit.py` on that run's raw data: the panel is rebuilt with the data truncated at 38 dates (every 6 months since 2008) and every complete month up to each cutoff must be identical to the full-sample panel (about 2.5 minutes). It does not block publishing; a failure opens an issue labelled `pit-check-failure`, which closes after the next passing check. This guards against the defect class found in the first code review (later SEC filings rewriting history), which only real data can expose.
* **Raw-input archive (private Cloudflare R2).** After each refresh, `engine/tools/archive_raw.py` stores every raw response the run used in a private R2 bucket, content-addressed as `blobs/<sha256>.gz` — the same SHA-256 the published manifests record — plus an index `runs/<run_id>-<attempt>-<scope>.json`; unchanged files are not uploaded again. `health.json → raw_archive.index` (and `stocks.json → run_issues.TW.raw_archive`) names the index of the run behind the published numbers. `engine/tools/restore_raw.py --index … --out DIR` rebuilds the cache (verifying every hash), after which `python -m tcd refresh --offline --cache DIR` recomputes that day. The bucket is private, so vendor data (Yahoo, Nasdaq) is archived but not redistributed. Credentials are repository **secrets** (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`), given only to the archive step; the bucket name is the variable `R2_BUCKET` (default `tech-cycle-raw`). Until the secrets exist the step is skipped; a failed upload never blocks publishing and opens a `raw-archive-failure` issue. Free tier (10 GB, free egress) is expected to last 2–3 years at the current volume; a lifecycle rule can cap retention.
* **Failure notifications.** A final `notify` job (only `issues: write`) reports each scheduled or manual run as GitHub issues, so failures reach the owner through the normal GitHub notifications instead of waiting for someone to notice the stale banner: a failed refresh / build / deploy opens (or comments on) an issue labelled `refresh-failure-full` or `refresh-failure-tw`; report-only components that failed open `refresh-degraded-<scope>`; the next clean run of the same scope comments "recovered" and closes it. Issues carry only the run link, the date and job / component names — never log text or error messages (`.github/scripts/notify.sh`).
* **Before every commit** `engine/tools/validate_data.py` checks that all JSON/CSV parse (no NaN), that the forecast ledger is a byte-prefix extension of the committed one (re-checked after any rebase), and that no e-mail address appears anywhere in `data/`.
* **Supply chain.** Dependencies are installed from `engine/requirements-dev.lock` (exact versions that passed the tests, SHA-256 hashes, `--require-hashes`). The write token is not persisted in `.git/config` while dependencies, tests and the engine run; it is passed only to the push. `SEC_USER_AGENT` is stripped, rejected if it contains control characters, and request errors never echo header values. GitHub Actions are pinned by major tag, not commit SHA (not changed in this round).
* **Concurrency.** Data refreshes queue in their own group and Pages deploys in another, so a push-triggered redeploy can no longer cancel a pending scheduled refresh.
* Partial (in-progress) month: shown as **provisional** regime; never enters the backtest.
* Walk-forward parameters for the live month = the fold for the current year (trained through last December), so live posture and backtest use the same rule.
* Provenance: `data/health.json` holds DQ results, per-source latest dates, the git commit actually checked out, the run mode (`live` / `offline`, `allow_stale`) and a SHA-256 manifest of the core raw files with full request URLs (headers are never recorded); the stock, cross-market and second-source files carry their own manifests or source URLs. Raw files are archived in a private R2 bucket by hash (see above), so a run can be re-verified and recomputed once the archive is configured. `data/history.csv` logs one row per run day.

```bash
cd engine
pip install --require-hashes -r requirements-dev.lock
python -m pytest -q tests
python -m tcd refresh --out ../data                                   # online
python -m tcd refresh --offline --out /tmp/tcd-out                    # reuse engine/.cache/raw; do not commit
python tools/validate_data.py --data ../data                           # the pre-commit checks
# Lockfile: edit requirements*.txt, then re-pin to versions that pass the tests:
#   pip-compile --generate-hashes --allow-unsafe --strip-extras -c <tested versions> -o requirements-dev.lock requirements-dev.txt
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
| v2 regime (live) | 0.11 | 2.4% | 14.3% | −71.9% | 1.91 |
| **v3 candidate** | **0.45** | 7.9% | 15.2% | **−56.6%** | 7.64 |
| Buy & hold | 0.39 | 8.5% | 23.0% | −80.5% | 8.98 |
| Vol-matched B&H (to v3, ex-post) | 0.39 | 6.9% | 15.2% | −62.8% | 5.98 |

(After the 2026-11-23 point-in-time fix, § 16; first run: v2 0.11, v3 0.46, v3 NAV 7.99.)

* v3 beats vol-matched buy & hold by ~0.06 Sharpe and ~6 pts of Max DD; P(v3 Sharpe > B&H Sharpe) = 0.74 from a paired block bootstrap, 90% interval of the difference [−0.09, +0.23] — **not statistically convincing**. (First run reported "PSR 0.64", which treated the B&H Sharpe as a known constant; § 16.)
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


## 10. Short-term risk: daily volatility and 95% VaR, plus a news (EPU) test (2026-11-23)

Module `engine/tcd/short_risk.py`; shown at the top of `risk.html`; stored in `data/risk.json → short_term`.

**Setup.** Daily log returns of the risk asset (XLK adjusted close, NDX before 1998-12). Targets: average daily variance over the next 1 and 5 trading days, proxied by squared close-to-close returns (no intraday data). Walk-forward, refit each January on days whose target window had ended; out-of-sample from 2000 (≈ 6,760 days).

| Model | Inputs |
|---|---|
| EWMA | RiskMetrics λ = 0.94 (no fitting; industry baseline) |
| HAR | 1-day, 5-day, 22-day realized variance (Corsi 2009) |
| HAR + VIX | + implied daily variance from VIX |
| HAR + VIX + EPU | + log 30-day mean of the daily news-based Economic Policy Uncertainty index (FRED `USEPUINDXD`), lagged one day because it is published the next day |

**Specification.** Primary: log-HAR (regression in logs, forecasts always positive, Duan smearing correction). Robustness: classic HAR on variance levels. A first run used levels only; with EPU it produced negative variance forecasts that were floored and blew up the QLIKE loss. The log form was adopted for *all* models for that reason, and every conclusion below is required to hold under both forms.

**Scoring.** QLIKE loss (robust to noisy variance proxies), Diebold-Mariano t with Newey-West variance. 1-day 95% VaR by filtered historical simulation (5% quantile of standardized returns of earlier out-of-sample forecasts, see below; EWMA uses the normal quantile), backtested with Kupiec (coverage) and Christoffersen (independence).

### Results (out-of-sample 2000 → 2026-11, log spec)

| Comparison | 1-day DM t | 5-day DM t | Reading |
|---|---:|---:|---|
| EWMA → HAR | +0.38 | +1.19 | no significant difference |
| HAR → HAR + VIX | **+5.38** | **+4.25** | VIX adds information |
| EWMA → HAR + VIX | **+3.74** | **+3.15** | live model beats the industry baseline |
| HAR + VIX → + EPU | −1.75 | −1.44 | EPU does not help (slightly worse) |

Level spec agrees: HAR + VIX better than HAR (t 2.83 / 4.07); EPU worse (t −2.38 / −1.02).

| 1-day 95% VaR (2000-01 → 2026-11, 6,762 days) | Breach rate | Kupiec p | Christoffersen p |
|---|---:|---:|---:|
| EWMA, normal | 5.99% | < 0.001 | 0.85 |
| HAR, FHS out-of-sample quantile | 4.70% | 0.26 | 0.28 |
| HAR + VIX, FHS out-of-sample quantile (**live**) | **4.76%** | **0.37** | 0.09 |
| HAR + VIX + EPU, FHS out-of-sample quantile | 5.29% | 0.27 | 0.45 |
| *HAR + VIX, FHS in-sample quantile (rule until 2026-11-23)* | *5.55%* | *0.043* | *0.16* |

* **VaR quantile fix (2026-11-23).** The original rule took the 5% quantile of *in-sample* standardized returns. In-sample fitted variances are optimistic, so in-sample standardized returns have thinner tails than real out-of-sample ones and the VaR was too low (5.55%, rejected at 5%). The fix, chosen on that principle and applied once without tuning: the quantile for year Y is the 5% quantile of standardized returns of the walk-forward forecasts made *out-of-sample* before Y whose outcome was known by the end of Y − 1 (expanding window; at least 500 days; forecasts now start in the first year with 1,000 training days so the burn-in ends before 2000). The live VaR uses all OOS residuals to date. Both rules are scored on the same days and both are published (`risk.json` → `short_term.evaluation.var95_by_quantile`).
* **Caveat.** The fix was diagnosed and checked on the same backtest window, so its in-sample improvement is not independent evidence. Supporting points: it improves every HAR variant, not only the live one, including EPU, which was not the target; the level spec stays within bounds (4.61%, p 0.14); the result is slightly conservative (4.76% < 5%), not tuned to 5%. Independent evidence will come only from live data.
* Live effect on 2026-11-20: 1-day 95% VaR 5.37% (old rule) → 5.50% (new rule).
* The EWMA/normal benchmark under-covers clearly: fat tails matter.

**EPU decision (pre-set rule: keep only if QLIKE improves with DM t ≥ 2 at every horizon, under both specifications): dropped.** Consistent with § 9: market-implied volatility already absorbs news faster than a daily newspaper index can add.

**Live output:** next-day and 5-day volatility and 1-day 95% VaR from the latest close; refreshed with the daily job. These describe the size of likely moves, not their direction.


## 11. Out-of-domain test of v3 (pre-registered 2026-11-23)

Module `engine/tcd/cross_market.py`; criteria committed in `3ac4e7d` before any real-data run; results on the Validation page and in `data/cross_market.json` (recomputed daily).

**Design.** The frozen v3 specification (same 1,080-configuration grid, walk-forward, objective, 15 bps costs) applied to nine markets it never saw: ^SOX (semiconductors, price index), SPY, XLF, XLE, XLV, EWJ, EWG, EWU, EEM (USD ETFs with dividends). Price-extension and volatility signals use each market's own prices; tech fundamentals only for ^SOX, neutral elsewhere. Each market warms up for seven years before its first out-of-sample year.

**Criteria.** C1: v3 Sharpe above vol-matched buy & hold in ≥ 6/9 markets. C2: mean Sharpe difference > 0 with a 90% joint calendar-block bootstrap CI excluding 0. C3 (secondary): smaller Max DD in ≥ 6/9. Pass = C1 and C2.

| Market | OOS from | v3 Sharpe | B&H Sharpe | Diff | v3 Max DD | Vol-matched Max DD |
|---|---|---:|---:|---:|---:|---:|
| ^SOX | 2008 | 0.68 | 0.71 | −0.02 | −24.7% | −26.4% |
| SPY | 2006 | 0.80 | 0.66 | **+0.14** | −12.9% | −33.7% |
| XLF | 2012 | 0.66 | 0.73 | −0.07 | −17.4% | −21.3% |
| XLE | 2012 | 0.14 | 0.38 | −0.24 | −55.1% | −37.5% |
| XLV | 2012 | 0.84 | 0.88 | −0.04 | −11.3% | −11.0% |
| EWJ | 2010 | 0.36 | 0.46 | −0.10 | −21.9% | −23.1% |
| EWG | 2010 | 0.22 | 0.32 | −0.10 | −22.5% | −24.9% |
| EWU | 2010 | 0.24 | 0.37 | −0.13 | −24.5% | −19.9% |
| EEM | 2017 | 0.36 | 0.39 | −0.03 | −28.5% | −28.3% |

**Verdict: FAILED.** C1 1/9; C2 mean −0.067, 90% CI [−0.158, −0.005] (significantly *worse*); C3 5/9.

Reading:
* The v3 edge on tech (+0.07 Sharpe, itself not significant, § 8) does not generalize; across other markets the same design costs about 0.07 Sharpe. This lowers confidence that the tech result reflects a real effect rather than luck and design hindsight.
* Context, not an excuse: most out-of-sample windows start in 2010–2012 and contain few large crises. The only winner, SPY, is the only window that includes 2008. This matches § 8: v3 behaves like insurance that pays in severe crises and costs return otherwise. Its drawdown reduction is the more consistent effect (5/9, and large in SPY), but it did not meet the 6/9 bar either.
* A constant, lower equity allocation with the same volatility (vol-matched buy & hold) did as well or better in 8 of 9 markets: on this evidence the simple alternative is "hold less", not "time the cycle".

**Consequences.** The promotion rule (model-promotion.md) is unchanged and still governs v3; this result is recorded as additional evidence against promotion and should weigh heavily if v3 is ever close to eligibility.


## 12. Daily risk light (plain-language summary)

Module `engine/tcd/light.py`; shown at the top of the home page in the reader's language; stored in `data/status.json → light`.

* **Rule (fixed):** tomorrow's HAR + VIX volatility forecast (§ 10) is ranked against every day's 22-day realized volatility since 1990, using data up to the latest close. Below the median → green; 50th–80th percentile → yellow; ≥ 80th percentile → red.
* **Text:** the engine writes codes and numbers only (level, percentile, ratio to the historical median, typical daily move, 1-day 95% VaR, month-to-date return, aggregate P/E state vs its 10-year average, earnings-momentum state). The page turns them into sentences from en / zh-TW templates in `js/i18n.js`, so both languages always show the same numbers and change automatically with each daily refresh.
* The light is built only on the volatility forecast, the one risk estimate with demonstrated out-of-sample skill. Valuation and earnings are shown as backdrop with an explicit note that they do not time crashes.
* The level is also logged daily in `data/history.csv` (`light` column).


## 13. Stock monitoring (US mega caps + Taiwan AI supply chain)

Module `engine/tcd/stocks.py`; list in `engine/watchlist.json` (edit it to add or remove names); page `stocks.html`; data `data/stocks.json`, refreshed daily (report only, never blocks the refresh). US names update with the 22:15 UTC run, Taiwan names also with the 07:07 UTC run; `stocks.json` keeps a per-market `updated` stamp and the page shows each market's last price date and update time. A market refresh replaces only that market's rows; a name that fails to fetch keeps its previous row flagged `stale: true` (counted on the page); if no name of the market can be analysed, the file is not written and nothing is committed (e.g. Taiwan holidays give no new bar, so no data change). **Risk monitoring only: no buy/sell signals and no per-stock strategy backtests.**

* **Universe (28):** AAPL, MSFT, AMZN, GOOGL, META, NVDA, ORCL, AMD, INTC, AVGO; Taiwan: 2330, 2454, 3661, 3443, 2317, 2382, 3231, 6669, 2356, 2308, 3017, 3324 (TPEx), 2059, 2345, 2383, 3037, 3711, 3131 (TPEx). Benchmarks ^NDX and ^TWII.
* **Model:** log-HAR on each stock's own daily returns (no VIX), EWMA 0.94 baseline, annual walk-forward refit; 1-day 95% VaR by filtered historical simulation. A VaR is **verified** only with ≥ 500 out-of-sample days and Kupiec and Christoffersen p ≥ 0.05.
* **Light:** same rule as the market light, against the stock's own history of 22-day realized volatility.
* **Other fields:** 1-month return, drop from the 52-week high, 1-year beta to the benchmark; for US names point-in-time SEC TTM revenue / net income and YoY growth (shown as "n/m" when the year-ago base is ≤ 0 or growth exceeds ±500%), trailing P/E, Capex / revenue, last filing date.
* **Data fixes found on the first real run (numerical, not tuned on results):** Yahoo carries Taiwan prices forward through halts and gaps (runs of unchanged closes up to 272 days) and has unadjusted corporate actions (a −80% day). Runs of ≥ 5 unchanged closes are removed, Taiwan daily moves beyond ±25% (impossible under the ±7%/10% limits) are dropped, the daily HAR term is floored at 5% of its 22-day mean, and the model is fitted on the next-5-day average variance. Before these fixes two stocks showed forecasts above 2,000% annualized.
* **First results (2026-11-23):** HAR beats EWMA (DM t > 0) for most names, but only **7/28 VaRs are verified** (MSFT, GOOGL, META, NVDA, INTC, AVGO, 3711). Most Taiwan failures are "breaches cluster": large moves come in runs (limit-down days follow each other), which a one-day model cannot anticipate. The page shows the failing reason per stock.
* **Known limits:** jumps around earnings releases are not forecastable; Taiwan names use prices only (no MOPS fundamentals); the list reflects today's leaders.

### 13b. Taiwan holiday bars removed from the model history (2026-11-23)

Module `engine/tcd/tw_calendar.py`, applied to Yahoo prices before the stock model (data layer; the model code and its `model_id` are unchanged). Yahoo's Taiwan stock series carry bars on days the exchange did not trade (national holidays, Lunar New Year, typhoon closures), usually the previous close repeated and sometimes a spurious price (e.g. 2330 on 2012-01-02: 75.8 → 69.8 → 70.5, a market holiday). The TAIEX series (`^TWII`) from the same source does not have them: its calendar matched the official TWSE calendar in 2025 (243/243 days) and never showed a bar on an official closure; where the official yearly list was incomplete (ad-hoc typhoon closures such as 2026-10-23), `^TWII` was the one that was right.

**Rule** (fixed before looking at its effect on the backtest and adopted regardless): inside the `^TWII` window (1997-07-02 →), drop a Taiwan stock bar if `^TWII` has no bar that day or `^TWII`'s close is unchanged from its previous bar (market-wide closure carried forward, e.g. 2001-09-18, 2014-07-23, 2016-07-08). Bars before the first or after the latest `^TWII` bar are kept. The second-source check (§ 15) still audits the raw Yahoo bars, so new holiday bars keep being reported.

Effect (2026-11-23): 1,130 bars dropped across 18 names (most before 2006); next-day volatility and VaR rise slightly (holiday zero returns had deflated them); no risk light changed; verified Taiwan VaRs stay at 1 (2382 crosses into "verified", 3711 drops out, both at the p ≈ 0.05 boundary). The removal is reported in `stocks.json` → `data_cleaning.tw_holiday_bars`. Limitation: bars before July 1997 (2317 only) are not checked.

### 13a. Tested and rejected: out-of-sample VaR quantile for stocks (2026-11-23)

After the market VaR fix (§ 10, out-of-sample FHS quantile), the same change was tested on the 28 stocks. Adoption rule fixed before looking at the results: adopt only if, on the same scored days, the number of verified names does not fall **and** the mean |breach rate − 5%| falls.

| | In-sample quantile (kept) | Out-of-sample quantile |
|---|---:|---:|
| Verified names (same days) | 9 | 4 |
| Mean \|breach rate − 5%\| | 0.66% | 0.69% |
| Mean breach rate | 5.20% | 5.43% |

**Rejected; the stock VaR keeps the in-sample quantile.** A first run also showed a population mismatch (the quantile included days with an unchanged close, which the backtest does not score); the run above fixes that and is the one the rule was applied to. Two attempts were made in total; no further variants were tried on this window.

Reading: unlike the market VaR, the stock VaR is not biased low on average (5.20%); most failures are **clustered breaches** (Christoffersen), which no choice of quantile can fix. A fix would need a variance model that reacts faster after a large move (e.g. an asymmetric or GARCH-type term, or the market's own volatility as a regressor), tested with a rule fixed in advance and, ideally, judged on the live ledger (§ 14) rather than on this backtest window.

## 14. Live forecast ledger and reconciliation (stocks)

Module `engine/tcd/ledger.py`; files `data/forecasts/stocks_ledger.csv` (append-only), `data/forecasts/stocks_outcomes.csv` (regenerated), `data/forecast_review.json`; section "Live track record" on `stocks.html`.

**Why.** The walk-forward backtest of section 13 is pseudo out-of-sample: it re-runs the current model over the past, and changes whenever the model changes. The ledger is the real record: forecasts written before the outcome exists.

**Ledger rules.**
* Every refresh (22:15 UTC full run and 07:07 UTC Taiwan run) appends, for each freshly analysed stock, the forecast for the next trading day: `origin_date` (date of the last close used), 1-day 95% VaR, HAR and EWMA next-day variance, risk light, engine version and `model_id` (sha256 of `stocks.py` + `StockConfig`, 12 hex).
* Key `(symbol, origin_date)`; the first forecast written wins. Existing bytes are never rewritten (checked before every write: the new file must start with the old file verbatim). Rows kept from a previous run (`stale`) are not forecasts and are not logged.
* A forecast is logged only if its bar is final: local time past 14:30 Asia/Taipei (TWSE closes 13:30) or 16:30 America/New_York. A manual run during trading hours logs nothing for that market.
* The ledger is committed by the daily job; the git commit time proves each forecast predates its outcome. No backfill: the record starts with the first run after this change.

**Scoring.** Each forecast is matched with the stock's next bar (adjusted close): log return `r`, breach if `exp(r) − 1 < −VaR`, QLIKE of the HAR and EWMA variances, variance ratio `r² / HAR variance`. Yahoo bars on days the exchange shows no trade (section 15) are skipped: they are never a forecast origin and never a target, so the forecast is scored against the next real trading day. Not scored: next bar not yet available (`pending`), more than 10 calendar days away (`gap`), Taiwan `|r| > 25%` (`data_error`, same rule as the model), origin bar missing from the source.

**Pre-registered review rules** (fixed now, before any live outcome exists; changing them is a documented, versioned change):

| Level | Minimum sample | Test | Verdicts |
|---|---|---|---|
| Market (US, Taiwan pooled) | 60 scored trading days | breach rate with a 90% CI clustered by date (names breach on the same days, so they are not independent) | CI above 5% → too many breaches; below → too few; contains 5% → consistent |
| Single stock | 250 scored days | Kupiec and Christoffersen, p ≥ 0.05 | consistent / coverage rejected / breaches cluster |

Also reported (descriptive, no verdict): variance ratio with clustered 90% CI (target 1.0), HAR vs EWMA per-date mean QLIKE difference with a Newey-West t, the last 60 days separately, and realized vs forecast volatility by risk-light level.

**Refinements of 2026-11-23 (review round 3; made before any outcome existed):**
* A forecast is logged only if its origin is a real trading day of the market benchmark (`^TWII`, `^NDX`: a bar exists and its close moved) and the model's data end on that same day (a halted or filtered stock is not logged). Targets are the next bar on a benchmark trading day; a bar after the benchmark's last bar waits.
* Outcomes with status `scored`, `gap` or `data_error` are **final**: kept exactly as first computed. A failed price fetch, a watchlist removal, a data revision or a non-trading day leaving the second-source window can no longer erase or change them; only `pending`, `no_price` and `origin_missing` rows are re-evaluated.
* CSV columns are read back as text (an all-digit `model_id` stays a string).
* Verdicts use only the current model's forecasts; other models are counted in `other_models`. `model_id` hashes the forecasting functions (incl. shared fitting code and the light rule) and `StockConfig`; a test pins the current id. The ledger's first 28 rows carry the old-formula id `333e22e1aab1`; their forecasting code was checked to be byte-identical to the current one, so `MODEL_ID_ALIASES` maps them to `9c9661d3517e`.
* Pooled confidence interval: deviations summed per date (names breaching on the same day) **and** Newey-West over the date-ordered sums with a 5-trading-day lag (breaches clustering over consecutive days). Date clustering alone was too narrow.

**No automatic recalibration.** Results never feed back into the model. If a verdict says the VaR is miscalibrated, a fix is a code change with a new `model_id`; the old rows stay in the ledger and the new model's record starts from zero.

Expected timing: market verdicts after about 3 months, single-stock verdicts after about 1 year. Until then the page shows "not enough data yet", which is not evidence for or against the model.

## 15. Second-source close check (Taiwan: official exchanges; US: Nasdaq)

Modules `engine/tcd/sources/twofficial.py`, `engine/tcd/official_check.py`; output `data/official_check.json`; one line in the Taiwan section of `stocks.html` and one line per stock in the detail panel. Report only: it never changes prices, the model or its outputs, and a failure never blocks a refresh.

* Sources: TWSE `rwd/zh/afterTrading/STOCK_DAY` (listed, `.TW`) and TPEx `afterTrading/tradingStock` (OTC, `.TWO`), one request per stock per month for the current and previous month, 2 s apart, one slow retry (15 s) after a throttled request (the exchanges answer bursts with HTTP 307). Raw responses go through the raw store (hashed, cached) like every other source.
* Compared with Yahoo's close (split-adjusted, not dividend-adjusted; official closes are unadjusted, so a corporate action inside the window shows as a difference, which is the intended alert):
  * **mismatch**: both have the day and |Yahoo / official − 1| > 0.5%;
  * **missing**: the exchange shows a trade, Yahoo has no bar;
  * **extra**: Yahoo has a bar on a day the exchange shows no trade (carried-forward price);
  * **not yet**: Yahoo bar after the exchange's latest published day (informational).
* Status per stock: `ok`, `warn` (any mismatch, missing or extra) or `unavailable`.
* Use in the forecast ledger (section 14): `extra` days are skipped as forecast origins and as scoring targets. This rule was added before any forecast had been scored.

First live run (2026-11-23, 18 names, 35 trading days each): zero price differences and no missing days; every name had one extra Yahoo bar on 2026-10-23, a day with no TWSE/TPEx trading, carrying the previous close forward.

**US second source (added 2026-11-23).** Module `engine/tcd/sources/nasdaq.py`: Nasdaq's public quote API (`api.nasdaq.com/api/quote/{symbol}/historical`), one request per stock for the same two-month window, consolidated closes for NYSE- and Nasdaq-listed names (it is an exchange operator's feed, not an independent audit, but it does not come from Yahoo). Same comparison rules and statuses as Taiwan; results for both markets live in `data/official_check.json` with a per-market `updated` stamp (each refresh replaces only its own market's rows). US runs with the 22:15 UTC full refresh; Taiwan with both runs. Stooq was considered and rejected: it now requires a browser JavaScript check, which an automated job should not bypass.

First US run (2026-11-23, 10 names × 37 trading days): zero price differences (largest gap 0.001%, rounding), no missing days, no extra Yahoo bars.

## 16. Independent code review and corrections (2026-11-23)

Four independent reviewers (point-in-time correctness, statistical methods, stock monitor and ledger, pipeline and security) read the code without being given the author's conclusions; every finding used here was reproduced before being accepted. Headline numbers that do not depend on the corrected code were recomputed independently from raw data and matched exactly (buy & hold CAGR 8.522%, vol 23.007%, Max DD −80.47%, Sharpe 0.3872; Kupiec p-values of all four VaR models).

**Corrected in this round (published numbers change):**

| Defect | Fix | Effect |
|---|---|---|
| SEC quarters: a direct 3-month fact filed later (comparative, restatement or mis-tagged annual value) replaced a quarter that could already be derived from year-to-date filings; share counts preferred a tag filed later over a count already public. The panel changed when later data arrived (14 of 38 cutoffs on real data). Tests only used synthetic data. | Earliest-available candidate wins for each period end (`fundamentals.quarterly`, `monthly_shares`); unit tests reproduce the real patterns (AAPL FY09 Q4, ORCL FY18 Q4, GOOGL shares); `engine/tools/check_pit.py` re-runs the truncation check on real cached data | 0 of 113 cutoffs differ. v2 OOS Sharpe 0.112 → 0.107; v3 0.458 → 0.447; v3 weight at 2026-10 0.19 → 0.16 |
| "PSR v3 vs B&H" plugged the sample B&H Sharpe in as a known constant | Paired moving-block bootstrap of the Sharpe difference (`validation.sharpe_diff_test`), also in the promotion post-window | v3: 0.64 → 0.74 (90% interval [−0.09, +0.23]); v2: 0.08 → 0.10. Conclusions unchanged |
| Signal study: Newey-West t (lag h−1) and 12-month block-bootstrap CIs over-reject with persistent signals and overlapping targets (simulated size 13–22% at a nominal 5%; CI miss rate ~20–25% at a nominal 10%, and longer blocks did not help) | Hodrick (1992) 1B t-stats (simulated size 5–7%); circular-shift test for quintile spreads, verdict at p < 0.05 (simulated false-positive rate 5–10%) | No IC with \|t\| ≥ 2 remains; verdicts revised (table in § 5, "v2.2 — stand-alone signal tests") |
| Stock VaR backtest dropped days with an unchanged next close (they cannot breach), inflating breach rates; the live ledger scores them | Backtest scores every day | Verified names stay 7: NVDA and 2382.TW drop out, AMD and 3131.TWO come in |
| "Aggregate P/E 18.4×" was a chain-linked index (≈ 25% below the level) | New `pe_level` = Σ market cap ÷ Σ TTM net income shown everywhere a P/E is quoted; the chain-linked series is kept only for the z-score | Light and dashboard show the actual level (≈ 25× at 2026-10) |
| Ledger `model_id` hashed all of `stocks.py` but not the shared fitting code | Hash of the forecasting functions (incl. `short_risk.design/fit_var`, `light.level_for`) + config | Forecast-irrelevant edits no longer change the id; changes to shared fitting code now do |

**v3 pre-registration.** The point-in-time fix changes `fundamentals.py`, which is part of the frozen v3 specification. Following the promotion rule (C5: a spec change resets the design date), the design date is reset to 2026-11-23 — the same day, so the first counted month stays 2026-12 and no post-design evidence existed yet. The fingerprint changes from `88e42dfd…ab61d` to `6855f924…fdb98e`; see the changelog in [model-promotion.md](model-promotion.md).

**Fixed in the second round (operations and security, no effect on published numbers):** report-only failures recorded in health.json and the banner; second-source outages keep the last good results; per-job concurrency groups; hash-pinned dependencies and no persisted write token; ci.yml with read-only permissions; freshness and no-new-bar gates on the Taiwan-only run; secret sanitising and redacted request errors; pre-commit data validation (strict JSON/CSV, append-only ledger against the previous commit, no e-mail addresses); git commit and run mode recorded; full request URLs in manifests; a real append check in the ledger. Not done: pinning Actions by commit SHA.

**Fixed in the third round (forecast ledger):** benchmark-calendar origins and targets, final outcomes frozen, text dtypes on read-back, verdicts per current model with a verified alias for the first rows, model-date check for halted names, CI robust to serial clustering; see § 14.

**Fixed in the fourth round (minor items):**

| Item | Fix | Effect |
|---|---|---|
| Sortino used the mean of squared returns over negative months only | Standard downside deviation over all months | Sortino v2 0.08 → 0.14, v3 0.44 → 0.66, B&H 0.37 → 0.57 (Sharpe unchanged) |
| `r2_log` short-risk diagnostic (log of single squared returns) | Replaced by the Mincer-Zarnowitz R² (`mz_r2`); `qlike` docstring corrected (the code's form differs from the textbook one by a constant) | Diagnostic only |
| Short-risk training cutoff used `BDay`, ignoring exchange holidays | Target window end taken from the actual trading-day index | VaR and variance results unchanged to the reported precision |
| Drawdown-model verdict depended on the bootstrap block length (3 episodes) | BSS interval = widest over 12/24/36/60-month blocks (`bss_ci90_by_block` published) | Verdict "no skill: worse than the base rate" → "no demonstrated skill"; the dashboard still shows the base rate |
| Month ending on an NYSE holiday flagged partial | NYSE holiday calendar (Good Friday, Memorial Day, …) for the last trading day | Live status only |
| Signal-study eras: 1993–2012 forward windows ran into 2013 | Windows must end inside the era | t-stats change by ≤ 0.03 |
| Promotion: a criterion that cannot be evaluated (C6 without history) led to `not_met` / `retire` | New state `undetermined` | — |
| No CSP; a few engine values inserted into HTML unescaped | CSP `<meta>` on every page (scripts and data same-origin only); remaining values escaped or whitelisted | Defence in depth |

The v3 fingerprint changed again (Sortino and calendar code are inside it): second same-day amendment in [model-promotion.md](model-promotion.md).

**Not changed, documented:** the stock walk-forward cutoff still uses `BDay` (378 of ~100,000 training rows reach past the cutoff; fixing it would change the stock `model_id` and restart the live record for a backtest-only effect); the next-month volatility forecast is the median of the log-normal forecast (`exp` of the log forecast, no smearing) — read it as a typical, not an average, level; cross-market `p_positive` is a bootstrap share, not a p-value; GitHub Actions are pinned by tag, not SHA.

**Known limitations, unchanged:** survivorship (today's ten leaders), design choices made after full-sample work, macro proxies from the latest FRED vintage. The market VaR, although it passes over 2000–2026 (4.76%), breached 7.15% of days over the last three years (Kupiec p 0.011); per the decision to judge stock and market VaR changes on live data, this is monitored, not tuned on the backtest.

## 17. Live forecast ledger for the market risk numbers (2026-11-23)

Module `engine/tcd/market_ledger.py`; files `data/forecasts/market_ledger.csv` (append-only), `data/forecasts/market_outcomes.csv`, `data/forecast_review_market.json`; section "Live track record" on `risk.html`.

**Why.** The market numbers the site trusts most were only kept in `history.csv`, whose row for a day is replaced by any later run the same day — not a record that proves a forecast preceded its outcome. They now get the stock ledger's treatment (§ 14): append-only, key `(target, origin_date)`, first write wins, bytes verified unchanged before every write and against the previous commit by `tools/validate_data.py`.

| Target | Logged | Scored against |
|---|---|---|
| `var_1d` | 1-day 95% VaR (simple return), HAR+VIX and EWMA next-day variance, risk light of the day; origin = last daily bar, only once the US close is final | next bar of the risk asset (XLK adjusted close): breach, QLIKE HAR vs EWMA, r² ÷ forecast variance |
| `vol_5d` | average daily variance over the next 5 days (HAR+VIX, EWMA) | mean r² of the next 5 bars |
| `vol_1m` | next-month realized volatility (annualized) and its 90% band; origin = a **complete** month-end only (provisional forecasts are never logged) | realized `rv21` of the next complete month: log error, inside-band |

**Pre-registered review rules** (fixed before any outcome exists): `var_1d` verdict after 250 scored days (Kupiec and Christoffersen, p ≥ 0.05 = consistent); `vol_1m` verdict after 24 months (90% band coverage within 80–97% = consistent, roughly the binomial 90% range at n = 24); `vol_5d` descriptive only. The last 60 days of `var_1d` are shown separately. Outcomes `scored` are final; verdicts use only the current model (`model_id`: hash of the forecasting code path and config — for `var_1d`/`vol_5d` also the name of the live HAR model; for `vol_1m` the monthly regression). No backfill; nothing feeds back into the models.

**First rows (2026-11-23):** `var_1d` and `vol_5d` from the 2026-11-20 close, `vol_1m` from the 2026-10-31 month-end. A `var_1d` verdict is due after about one year, the first `vol_1m` verdict after two. The recent under-coverage of the market VaR (§ 16: 7.15% over the last three years) will be judged on this record, not on the backtest.

## 18. Pre-registered challenger for the market VaR (2026-11-23)

Module `engine/tcd/var_challenger.py`; registered in commit `a6f4a2e` (2026-11-23 13:58 UTC) **before any result of the challenger was computed**.

* **Problem.** The live VaR's quantile comes from an **expanding** window of all earlier out-of-sample standardized returns (live: updated daily; in the backtest: once a year — both give 7.14% over the last three years, so the cause is the expanding window, not the update frequency; corrected 2026-11-23, the first version of this section said "updated yearly"). It covers over 2000–2026 (4.76%) but breached 7.15% of days over the last three years (Kupiec p 0.011, § 16).
* **Challenger (the only one).** Same HAR+VIX variance; quantile = 5% quantile of the last **500** out-of-sample standardized returns (≈ 2 years), updated daily. 500 was fixed on that principle and will not be tuned; a different window would be a new challenger with a new registration.
* **Live comparison.** Both are logged in the market ledger (§ 17) as `var_1d` and `var_1d_challenger` with their own `model_id`s and scored on the same days.
* **Decision rule (fixed at registration).** After ≥ 250 live days scored for both: recommend switching **only if** the incumbent fails (Kupiec or Christoffersen p < 0.05) **and** the challenger passes both; otherwise keep the incumbent. The owner decides; nothing switches automatically. Shown in `forecast_review_market.json → challenger_comparison` and on the risk page.
* **Backtest — context only, not evidence** (the same window was used to find the problem, so the challenger is expected to look better on it):

| Window | Incumbent | Challenger |
|---|---|---|
| 2000-01 → 2026-11 (6,762 days) | 4.76%, Kupiec p 0.37, Christoffersen p 0.09 | 5.31%, p 0.25, p 0.47 |
| Last 3 years (756 days) | 7.14%, p 0.011 | 6.22%, p 0.14 |

Current 1-day VaR (2026-11-20): incumbent 5.50%, challenger 5.98%. The site keeps showing the incumbent.

## 19. Second code review: ledgers, challenger, notifications (2026-11-23)

Three independent reviewers read the code added after the first review (§ 16: ledger hardening, minor fixes, market ledger, challenger, notifications) without the author's conclusions. The two critical findings were reproduced before fixing. No outcome had been scored in either ledger at the time, so every rule change below predates all live results.

| Finding | Fix |
|---|---|
| **Outcomes could be scored against an unfinished (intraday) bar and then frozen** (both ledgers; a manual run during a session would do it; a month-end intraday bar also made a month look complete). No damage: all of today's runs started before the US open and every outcome was still `pending`. | The target bar must be final (`bar_is_final` of the target day; for `vol_1m` the target month's last NYSE trading day), otherwise the outcome stays `pending`; a `vol_1m` forecast is logged only after its month's last trading day has closed. |
| **Pooled stock-ledger CI under-covered at the 60-date gate** (simulated 66–85% for a nominal 90%; false "too few" 2–5× nominal). Two replacements were simulated against a rule fixed in advance (false-positive rate ≤ 7.5% on each side): neither controlled the "too few" side when names breach together. | The pooled verdict is now **one-sided**: "too many breaches" by a z-test whose SE is computed from deviations from 5% (summed per date, Newey-West over dates, floored at the binomial SE) — simulated false-positive rate ≤ 7.2%. "Too few" is not tested; the interval is descriptive. Single stocks and the market VaR keep Kupiec + Christoffersen. |
| `model_id`s missed module constants (`LOGGED`, `FEATURES`, `HAR_FEATURES`, `_ols`), the Taiwan data cleaning and, for `vol_1m`, the definition of its inputs (`rv`/`VIX` lines of `build_panel`, `FeatureConfig`); the alias for the first 28 stock rows covered identical code but rows produced before the Taiwan holiday-bar cleaning | Ids now cover these; the challenger id covers the shared variance code and its own quantile only. **The alias was removed**: the 28 stock rows and the 4 market rows of 2026-11-23 are counted as an earlier model, and the live record restarts with the next run. |
| Benchmark fetch failure let holiday bars become origins/targets | No benchmark → no logging and no scoring (`pending`). |
| Frozen outcomes re-parsed as floats (last-digit drift) | Outcome files are read as text, so frozen rows are written back byte-identical. |
| `vol_1m` band verdict flagged a perfect 24/24 | Exact two-sided binomial test of coverage = 90% (p ≥ 0.05). |
| Missing VaR scored as "no breach"; missing EWMA field aborted logging; challenger errors could stop the refresh; `None` p-values could crash the decision rule | `invalid` status; tolerant field access; challenger wrapped (report-only); `insufficient` when tests are not computed. |
| BSS "90% CI" over several block lengths is not a 90% interval | Relabelled as a robustness range (`bss_ci90_basis`). |
| Promotion: `undetermined` could outlive the retirement deadline | Retirement is checked first. |
| Notifications: scope fell back to `full` when the refresh died early; cancelled jobs reported as plain failures with wrong text; a crash after closing the failure issue; an older run could close a newer failure; a Taiwan holiday run reported stale component state | Scope derived from the trigger inside `notify`; text distinguishes cancelled/failed and what was published; status-file errors handled; `notify` jobs serialised and an issue is closed only if it had no activity after the run started; status files older than the run are not evaluated. |
| Push token in the URL ended up in the runner's git reflog | Token passed as an HTTP header per command. |
| `validate_data.py` skipped the ledger check when git failed | An unresolvable base ref is an error. |
| A few numbers inserted into HTML unescaped | Escaped. |

**Known limitations (documented, not changed):** Christoffersen is applied to logged days, which can have gaps (failed runs, no backfill); incumbent and challenger rows for one day may come from different data vintages if one is added by a re-run; a lagging benchmark drops that day's forecasts (not recovered) and the after-window Taiwan rule can drop a real unchanged-close bar for one run; Yahoo's dividend adjustment may lag the ex-date, so a return scored on an ex-dividend day can include the dividend drop; the e-mail check in `validate_data.py` does not catch encoded addresses; a `<meta>` CSP cannot set `frame-ancestors` (GitHub Pages sets no headers).

## 20. Earlier live verdicts: interim looks and a multi-market panel (registered 2026-11-23)

Registered in the commit that adds this section, **before any live outcome existed and before the panel's results were computed** (modules `engine/tcd/sequential.py`, `engine/tcd/var_panel.py`).

**Why.** A 95% VaR breaches on 1 day in 20, so one series yields few events: after 250 days (≈ 12 expected breaches) a true rate of 7% is detected with less than even odds; ≈ 730 days are needed for 80%. Waiting a year gives a verdict, but a weak one.

**A — interim looks (early warning).** Verdicts on "too many breaches" are taken only at fixed looks with a split error budget; re-testing a growing sample every day would inflate false alarms (this also replaces the daily re-test of the pooled stock verdict of § 14):

| Look (scored days or dates) | 60 | 120 | 250 |
|---|---:|---:|---:|
| One-sided alpha | 1% | 1.5% | 2.5% |
| Single series (market VaR, challenger): breaches in the first *n* days ≥ | 8 | 13 | 21 |

Pooled series (stock ledger per market, panel below) use the null-centred, date-summed Newey-West z-test of § 19 on the first *n* dates at the same alphas. A warning, once raised at a look, stays raised. Simulated overall false-alarm rate: single series 2.4% (independent breaches), 5.0% (mild clustering), 8.6% (strong clustering, which Christoffersen flags separately); pooled 1.1–5.0%. Power of the single series: true rate 10% → 24% by day 60 and 84% by day 250; 12% → 43% and 97%. **The 3-month look catches only gross under-coverage.** The Kupiec + Christoffersen verdict at 250 days (§ 17) and the challenger rule (§ 18) are unchanged.

**B — multi-market panel of the VaR method.** The live VaR's method without the VIX term (VIX measures US large-cap volatility only): log-HAR on (rv_d, rv_w, rv_m) of each series' own daily log returns, one-day target, annual walk-forward refits, Duan smearing, 1-day 95% VaR from the 5% quantile of all earlier out-of-sample standardized returns (≥ 500). Series: `^NDX ^SOX SPY XLF XLE XLV EWJ EWG EWU EEM` (Yahoo adjusted close; already fetched for § 11). Logged daily in the market ledger as `panel_var_1d:<symbol>` (own `model_id`), scored on each series' next bar after the US close is final. Pooled verdict at the interim looks above; with ten correlated series the first look (60 dates ≈ 3 months) has far more breaches than the single series. It judges the **method**, not the XLK VaR on the site. Its backtest per series is published as context only (`backtest_context`).

**First computed results (after registration, 2026-11-23; backtest = context only).** Panel 1-day 95% VaR backtest breach rates over the full history: ^NDX 5.04%, ^SOX 4.94%, SPY 4.74%, XLF 5.02%, XLE 4.83%, XLV 5.71%, EWJ 4.81%, EWG 5.39%, EWU 4.64%, EEM 4.07%; over the last three years all between 3.8% and 5.2% except ^SOX (6.48%). Read with care: this backtest was not used to choose the method, but it is not live evidence either. Ten panel forecasts were logged from the 2026-11-20 close.

## 21. Volatility-based exposure cap and risk alerts (registered 2026-11-23)

Registered in the commit that adds this section, **before the cap's or the alerts' history was computed** (modules `engine/tcd/exposure.py`, `engine/tcd/alerts.py`). Neither changes v2 (the live posture) or v3 (its specification fingerprint and promotion clock are untouched); both are display and notification only.

**Why a volatility cap.** The site's tests show that valuation, Capex and earnings do not time crashes (§ 2.2, § 9.1); the one risk estimate with demonstrated out-of-sample skill is the volatility forecast (§ 9.2, § 10). A position-control number is therefore built on that forecast only.

**A — suggested maximum exposure (fixed rule).**

```
sigma_hat = live 5-day volatility forecast of the risk asset, annualized (HAR + VIX, § 10)
target    = median 22-day realized volatility of all days since 1990 up to the latest close (point-in-time)
cap       = min(1, target / sigma_hat), rounded DOWN to a 5-point step
band      = A (100%)  B (75-95%)  C (50-70%)  D (25-45%)  E (below 25%)
```

Meaning: "hold at most the exposure that carries the risk of a typical day". It is a ceiling, not an instruction to trade; it uses no leverage, no costs and reports no return or Sharpe headline. Logged daily in the market ledger as `exposure_cap_5d` (decision record, append-only; columns reused: `har_var` = 5-day variance forecast, `vol_ann` = target volatility, `band_lo` = unrounded cap, `band_hi` = published cap, `level` = band). Scored after 5 trading days: `ratio` = cap × realized 5-day volatility / target (1 = risk on target), `in_band` = ratio ≤ 1.5, `log_error` = log(ratio). Summary only (n, median ratio, share above 1.5); the forecast itself is tested as `vol_5d`.

Backtest context (out-of-sample walk-forward 5-day forecasts from 2000, target point-in-time, cap applied to the next day's return): average cap, share of days below 100%, realized volatility and maximum drawdown with and without the cap, and the same four drawdown windows for every run (2000-03 → 2002-10, 2007-10 → 2009-03, 2020-02 → 2020-03, 2022-01 → 2022-10). Context only; nothing is tuned on it.

**B — alerts.** Computed by the engine after each full refresh (`data/alerts.json`), compared with the previously published state, and posted as a comment on one open GitHub issue labelled `risk-alert` (the owner is notified; the issue is never closed automatically). Events, all on a new US close only (a same-day re-run cannot repeat them):

| Event | Rule |
|---|---|
| `light_change` | risk light level differs from the previous close's level (§ 12) |
| `cap_band_change` | exposure-cap band differs from the previous close's band |
| `var_breach` | a live 1-day 95% VaR (`var_1d`, current model) was newly scored as breached |
| `validation_warning` | an interim look (§ 20) of `var_1d`, `var_1d_challenger` or the panel newly reads `too_many_at_N` |

No hysteresis is applied to the light or the cap now (changing the light's rule would change § 12). Their historical stability is measured instead, from the same walk-forward forecasts (light: 1-day forecast vs point-in-time history of 22-day realized volatility): changes per year, median run length, and the share of changes reversed within 5 trading days. **Registered review rule:** if either series averages ≥ 24 changes per year or ≥ 30% of its changes reverse within 5 trading days, a display buffer is proposed to the owner (not applied automatically).

**First computed results (after registration, 2026-11-23; backtest = context only).** Cap at the 2026-11-20 close: 35% (band D; forecast 5-day volatility 53% vs median 19%). Walk-forward 2000-01 → 2026-11: average cap 84%, below 100% on 50% of days; realized volatility 17% with the cap vs 26% without; maximum drawdown −69% vs −82% (dot-com −69% vs −82%, financial crisis −36% vs −53%, COVID −14% vs −31%, 2022 −22% vs −32%). **Most of that reduction comes from holding less on average:** a constant exposure with the same realized volatility (66.6%, chosen ex-post) has drawdowns of −66% / −39% / −21% / −22% in the same windows and −66% overall. The cap adds a clear benefit only in fast shocks (COVID, partly 2008), none in the slow dot-com decline, and a higher return than that constant exposure (7.0% vs 5.8% a year, no costs). Stability: the light changed about 20 times a year (median run 3 trading days, 62% of changes reversed within 5 days); the cap band about 22 times a year (median 3 days, 55% reversed). **Both exceed the registered review threshold (≥ 30% reversed)**, so a display buffer is proposed to the owner; until a decision, alerts fire on every change.

**Amendment 1 (2026-11-23, owner decision "option A"; registered before its effect was computed).** The review rule above was triggered, and the owner chose to buffer the **alerts only**; the light (§ 12) and the cap shown on the site are unchanged. A `light_change` or `cap_band_change` alert is sent only after the new level has held for **2 consecutive closes**; the reference is the last *confirmed* level, not the previous close (a red → yellow → red round trip within one close raises nothing; red → yellow → green raises nothing until one of them holds for two closes). The filter state is stored in `data/alerts.json → state`; on the first run it starts from the last published level, so the switch raises no alert. VaR breaches and interim-look warnings are not buffered. The alert frequency and the reversal share under this rule are computed from the same walk-forward history and published as context.

*Effect of amendment 1 (computed after it was registered; context only).* With the 2-close confirmation, light alerts fall from about 20 to 10 a year and cap-band alerts from about 22 to 12 (median run of the confirmed level 9 trading days instead of 3). The share of confirmed changes reversed within 5 trading days is still 34% (light) and 30% (cap), at or just above the 30% review line; no further change is made on this result (choosing a longer confirmation now would be fitted to it).
