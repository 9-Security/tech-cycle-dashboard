# Tech-cycle prediction / scenario Agent

Domain assistant that reads the **live status API** (and/or `data/live/latest/`) plus project context, then writes **forward-looking risk narratives** (base / overheat / shock). It does **not** issue trade-execution signals.

| Item | Value |
|------|--------|
| Slug | `tech-cycle-forecast` |
| Model (when credentialed) | `grok-4.7` · high reasoning · fast |
| Deterministic fallback | `predict_scenarios.py` |
| Status API | `http://127.0.0.1:8765/api/status/latest` |

Baked scenarios in this repo: [`data/scenarios.json`](../data/scenarios.json).

## Defaults

- Purpose: domain assistant over tools/APIs  
- Channels: playground + HTTP; daily schedule after refresh (~06:30 UTC)  
- Tools: `get_live_status`, `get_status_history`, `get_project_context`  
- Smoke eval needs a Cursor credential for the model turn  

## How to refresh data first

```bash
PYTHONPATH=. python3 refresh_live.py            # or --skip-fetch
PYTHONPATH=. python3 dashboard/app.py           # :8765
```

## Run — Agent SDK (when credentialed)

```bash
npx --yes "@grok/agent-sdk@0.7.2" validate --dir .
npx --yes "@grok/agent-sdk@0.7.2" tool call get_live_status --dir . --input '{"prefer":"auto"}' --json
npx --yes "@grok/agent-sdk@0.7.2" run --dir . --message \
  "Give me the current tech Capex cycle risk scenarios for the next 3–6 months."
```

## Run — deterministic fallback (no Cursor key)

```bash
python3 predict_scenarios.py
python3 predict_scenarios.py --out scenario_brief.json --markdown-out scenario_brief.md
```

Fail-closed: missing status or non-`REAL` `DATA_SOURCE` aborts (no silent mock).

## Output shape

1. **As of** — `as_of`, `DATA_SOURCE`, `panel_end`, regime, VIX, overheat, lag-1 `recommended_weight` vs `target_weight`  
2. **Regime interpretation** — near-term Capex-cycle risk reading from live signals  
3. **Scenarios (3–6 months)** — `base` / `overheat` / `shock` with engine-consistent defensive postures  
4. **Disclaimer** — scenario analysis only; not investment advice; not auto-trading  

Lag-1 rule: `recommended_weight` is already in force; `target_weight` is the latest month-end signal not applied same-month.
