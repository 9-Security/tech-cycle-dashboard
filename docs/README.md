# Documentation

## Current (engine v2 — live)

| Doc | Topic |
|-----|--------|
| [methodology.md](methodology.md) | **Start here.** Data, point-in-time rules, regimes, nested walk-forward, first live results, limitations, operations |
| [model-promotion.md](model-promotion.md) | Pre-registered rule for switching the live model from v2 to the v3 candidate |

Live numbers are in `data/validation.json` and on the Validation page; they change daily.

## Historical (v1 — Cursor prototype, in-sample tuned)

These describe the earlier Python package (not in this repo) and its baked snapshot (Sharpe ~0.66, in-sample). v2 reproduces that figure in-sample (≈0.67) and shows it does not survive walk-forward. Kept for provenance.

| Doc | Topic |
|-----|--------|
| [project-context.md](project-context.md) | Original strategy goal and four regimes |
| [backtest-run-report-filing-dates.md](backtest-run-report-filing-dates.md) | v1 filing-date run (Sharpe 0.66) |
| [backtest-run-report-tuned.md](backtest-run-report-tuned.md) | v1 defense tuning (368 configs, full sample) |
| [real-data-wiring.md](real-data-wiring.md) | v1 producer contract |
| [package-readme.md](package-readme.md) | v1 package layout |
| [dashboard.md](dashboard.md) / [live-status-api.md](live-status-api.md) | v1 Flask UI and status API |
| [prediction-agent.md](prediction-agent.md) | v1 scenario agent |
| [dashboard-publish.md](dashboard-publish.md) | v1 static publish (apps.grok.bot) |
| [code-review.md](code-review.md) | v1 pre-fix review |
