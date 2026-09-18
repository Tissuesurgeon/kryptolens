# Architecture

KryptoLens is a modular Django monolith. The product path is an authenticated **Lens** workspace. **Job** in the UI is a `LensRun`. Django `Job` remains the standing 1:1 assignment. `IntelligencePolicy` stays an internal compiled artifact. The user does not choose capabilities.

```
User
  → Lens conversation
  → Understanding Agent (LLM JSON → ClarifiedTask)
  → Chief Agent → CapabilityPlan
  → TaskCompiler → Workflow
  → AgentRuntime (PLAN ACT OBSERVE VERIFY REPAIR COMPLETE)
    → AgentTask → LensRuntime → Tool registry → CMC
    → Observation rows → capabilities (Market, Anomaly, Reaction, Historical, Discovery, Regime)
    → Deterministic analysis → Evidence → Verification → Response Agent
    → Same Lens thread
```

Request → capability plan → registered CMC tool → API response → deterministic calculation → verified result. No fake or demo market data.

Legacy trigger-only Lenses still use `MonitoringService.run_lens` inside `LensRuntime`. Check now and Beat enter `AgentRuntime` then `LensRuntime`.

Run now creates a `LensRun` (`stage=queued`), queues the same Celery task, and returns `run_id`. The UI polls `LensRun.stage`.

## Locked rules

- Policy JSON field names stay frozen: `metrics`, `asset_conditions`, `market_context`. UI copy may say “Signals.”
- No mock CoinMarketCap data on the product path. Fixtures live under `tests/fixtures/`.
- The LLM understands the user message. Heuristics run only when the provider is non-LLM, the call fails, or the JSON is invalid. Chief Agent plans capabilities and tools from `ClarifiedTask`. Chief does not call CMC.
- Capabilities are internal analytical modules. `onchain` / `defi` / `risk` / `security` are architectural boundaries, not personas. News is CMC Content Latest.
- Scoring is deterministic (`apps/intelligence/scoring.py`). The engine calls it; `evaluate_policy` is not replaced.
- Zero events is a successful scan. The summary is persisted so the workspace can say so.

## Layout

| Path | Role |
| --- | --- |
| `apps/intelligence/` | ClarifiedTask, CapabilityPlan, ChiefAgent, compiler, AgentRuntime, verification, permissions |
| `apps/cmc/` | Adapter, normalizer, `CmcCallLog` |
| `apps/monitoring/` | Beat → AgentRuntime → LensRuntime; async Check now |
| `apps/lenses/` | Lens, Job, Artifact, Evidence, AgentTask, ApprovalRequest, conversation |
| `apps/events/` | Receipts |
| `apps/notifications/` | Telegram isolate-on-failure |
| `templates/workspace/` | Persistent roster + conversation artifacts |

## Run stages

Happy path: `queued` → `investigating` → `loading_policy` → `fetching_cmc` → `evaluating` → `verifying` → `complete`

Repair (once): `repairing` after empty CMC / missing trigger / `needs_more_evidence`. Inconclusive is not an error.

CMC failure: `fetching_cmc` → `error`

The frontend only reflects the database.

## Deployment

Local: SQLite + `python manage.py runserver`. Scheduled and async **Run now** need Redis plus a Celery worker (`celery -A config worker -l info`) and Beat (`celery -A config beat -l info`).

Compose (`docker compose up --build`) starts Postgres, Redis, web, worker, beat, and Nginx at [http://localhost:8080](http://localhost:8080). Set `CMC_API_KEY` in `.env`. Without it, Run now persists `stage=error` instead of inventing ticks.

Never commit `.env`. Users sign up and log in. There is no operator/demo account.

Supabase: public Django tables have row-level security enabled (no policies), including `lenses_lens`. PostgREST cannot read them; Django still can as table owner.
