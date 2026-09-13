# Architecture

KryptoLens is a modular Django monolith. The product path is a persistent-agent workspace over a frozen Intelligence Policy.

```
Human intent → Intent Agent → IntelligencePolicy → QueryPlan
→ CMC Adapter → MarketObservation / MarketContext
→ Policy engine → Scoring → Event → Explanation Agent → Receipt
→ Web conversation + optional Telegram
```

Beat and **Run now** share `MonitoringService.run_lens`. Run now creates a `LensRun` (`stage=queued`), queues the same Celery task, and returns `run_id`. The UI polls `LensRun.stage`.

## Locked rules

- Policy JSON field names stay frozen: `metrics`, `asset_conditions`, `market_context`. UI copy may say “Signals.”
- No mock CoinMarketCap data on the product path. Fixtures live under `tests/fixtures/`.
- Two agents only: Intent (NL → policy) and Explanation (facts → brief).
- Scoring is deterministic (`apps/intelligence/scoring.py`). The engine calls it; `evaluate_policy` is not replaced.
- Zero events is a successful scan. The summary is persisted so the workspace can say so.

## Layout

| Path | Role |
| --- | --- |
| `apps/intelligence/` | Policy, compiler, planner, engine, scoring, explanation |
| `apps/cmc/` | Adapter, normalizer, `CmcCallLog` |
| `apps/monitoring/` | `run_lens`, Celery Beat + async Run now |
| `apps/lenses/` | Lens, version, run artifacts (`stage`, `summary_json`, `near_matches_json`) |
| `apps/events/` | Receipts |
| `apps/notifications/` | Telegram isolate-on-failure |
| `templates/workspace/` | Persistent roster + conversation artifacts |

## Run stages

Happy path: `queued` → `loading_policy` → `fetching_cmc` → `evaluating` → `scoring` → `complete`

CMC failure: `fetching_cmc` → `error`

The frontend only reflects the database.

## Deployment

Local: SQLite + `python manage.py runserver`. Scheduled and async **Run now** need Redis plus a Celery worker (`celery -A config worker -l info`) and Beat (`celery -A config beat -l info`).

Compose (`docker compose up --build`) starts Postgres, Redis, web, worker, beat, and Nginx at [http://localhost:8080](http://localhost:8080). Set `CMC_API_KEY` in `.env`. Without it, Run now persists `stage=error` instead of inventing ticks.

Never commit `.env`. Operator login is `APP_EMAIL` / `APP_PASSWORD`.
