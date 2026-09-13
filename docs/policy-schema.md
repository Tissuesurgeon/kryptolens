# Policy schema

`IntelligencePolicy` is the core domain object. Stored on `LensVersion.policy_json`. **Field names are frozen.** Do not rename `metrics`, `asset_conditions`, or `market_context` to `signals` / `conditions`.

```json
{
  "version": 1,
  "name": "Top-100 Momentum",
  "universe": {
    "type": "listings",
    "limit": 100,
    "exclude_stablecoins": true,
    "symbols": []
  },
  "metrics": {
    "observed": ["price_change_24h", "volume_change_24h", "market_cap_rank"],
    "context": ["fear_greed"],
    "derived": ["rank_improved"]
  },
  "asset_conditions": [
    {"metric": "price_change_24h", "operator": ">", "value": 5},
    {"metric": "volume_change_24h", "operator": ">", "value": 80}
  ],
  "logic": "AND",
  "market_context": [{"metric": "fear_greed", "operator": ">=", "value": 70}],
  "min_notify_severity": "medium",
  "actions": ["store_event", "notify_telegram"],
  "assumptions": ["Stablecoins excluded."],
  "summary": "",
  "interesting_event": "Strong price movement + unusual volume"
}
```

Ask-vs-assumed metadata lives on `LensVersion.compile_report_json`, not inside `policy_json`.

## Near-match artifact

`LensRun.near_matches_json` holds up to ~20 objects. Templates only render `passed` / `actuals`.

```json
{
  "symbol": "SOL",
  "name": "Solana",
  "actuals": {"price_change_24h": 6.2, "volume_change_24h": 71},
  "conditions": [
    {"metric": "price_change_24h", "operator": ">", "threshold": 5, "passed": true},
    {"metric": "volume_change_24h", "operator": ">", "threshold": 80, "passed": false}
  ]
}
```
