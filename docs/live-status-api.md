# Live refresh + status API

Scheduled/manual data refresh and a current-status JSON API on top of the fixed/tuned tech-cycle package.

> The **published** app in this repo is a **static bake** of one snapshot. The Flask API below is the local / self-hosted path for live refresh.

## Refresh pipeline

```bash
# Full refresh (default): fetch public panel → lag-1 prototype → live snapshot
PYTHONPATH=. python3 refresh_live.py

# Offline / smoke: reuse existing data/raw (still fail-closed, DATA_SOURCE=REAL)
PYTHONPATH=. python3 refresh_live.py --skip-fetch
```

**What it writes**

```
data/live/<UTC as_of>/
  prototype_backtest.csv
  prototype_overall.csv
  status.json
  raw_manifest.json
data/live/latest/          # copy of newest snapshot
data/live/history.jsonl    # append-only metadata rows
```

Fail-closed: missing raw CSVs, DQ failure, or non-`REAL` data source aborts without updating `latest/`. No silent mock.

## Scheduler (daily)

Default cadence: **daily** (example 06:15 UTC).

```cron
15 6 * * * cd /path/to/tech_cycle_backtest && PYTHONPATH=. python3 refresh_live.py >> data/live/refresh.log 2>&1
```

## Status API (port 8765)

```bash
PYTHONPATH=. python3 dashboard/app.py
```

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/health` | Liveness + `as_of` + data paths |
| GET | `/api/status/latest` | Current regime, lag-1 weights, VIX/overheat, metrics |
| GET | `/api/history?limit=20` | Recent snapshot metadata |
| GET | `/api/series` | Full chart series (dashboard) |

### Lag-1 weight semantics

`recommended_weight` (= `executed_weight` / `risk_weight`) is the **lag-1** position that would earn the *next* period’s return.  
`target_weight` is the signal from the latest panel month’s regime (known at month-end; not applied same-month).

### Example shape: `GET /api/status/latest`

```json
{
  "as_of": "20261121T035000Z",
  "DATA_SOURCE": "REAL",
  "panel_end": "2026-10-31",
  "regime": { "code": 4, "label": "Normal" },
  "weights": {
    "target_weight": 1.0,
    "executed_weight": 0.5897,
    "recommended_weight": 0.5897,
    "note": "recommended_weight is lag-1 executed risk weight (no same-month look-ahead)."
  },
  "signals": {
    "vix": 19.42,
    "overheat_score": 1.176,
    "shock_flag": 0
  },
  "metrics": {
    "sharpe": 0.66,
    "max_dd_pct": -23.8,
    "cagr_pct": 5.76,
    "final_nav": 5.033
  }
}
```

Static equivalents in this repo: [`data/status.json`](../data/status.json), [`data/health.json`](../data/health.json).
