# Architecture

KryptoLens is a modular Django monolith. The product path is an authenticated Agent workspace. **Agent** is the UI name for a `Lens`. **Job** in the UI is a `LensRun`. Django `Job` remains the standing 1:1 assignment. `IntelligencePolicy` stays internal.

```
User instruction → ConversationAgent → ClarifiedTask → ChiefAgent → Job + AgentPlan
  → Validator → Workflow
    → AgentRuntime (PLAN ACT OBSERVE VERIFY REPAIR COMPLETE)
      → AgentTask → LensRuntime → Crypto Tool Layer → CMC
      → Observation rows → hidden capabilities → Evidence → Verification → Response LLM
      → Conversation
```

Legacy trigger-only Lenses still use `MonitoringService.run_lens` inside `LensRuntime`. Check now and Beat enter `AgentRuntime` then `LensRuntime`.

Run now creates a `LensRun` (`stage=queued`), queues the same Celery task, and returns `run_id`. The UI polls `LensRun.stage`.

## Locked rules

- Policy JSON field names stay frozen: `metrics`, `asset_conditions`, `market_context`. UI copy may say “Signals.”
- No mock CoinMarketCap data on the product path. Fixtures live under `tests/fixtures/`.
- The LLM understands the user message (snapshot vs standing job, assets, stated thresholds). Chief Agent plans from that understanding. Explanation remains an LLM use. Chief does not call CMC.
- Specialists `onchain` / `defi` / `risk` / `security` are architectural boundaries, not fake agents. News is CMC Content Latest, not a specialist persona.
- Scoring is deterministic (`apps/intelligence/scoring.py`). The engine calls it; `evaluate_policy` is not replaced.
- Zero events is a successful scan. The summary is persisted so the workspace can say so.

## Layout

| Path | Role |
| --- | --- |
| `apps/intelligence/` | Policy, compiler, ChiefAgent, AgentPlan, AgentRuntime, verification, permissions |
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
