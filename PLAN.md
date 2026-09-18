# KryptoLens build plan

Authenticated persistent-agent workspace. There is no demo product.

## What it is

KryptoLens is a persistent crypto intelligence workspace where users create Lenses, talk to them in natural language, give them crypto-market jobs, and leave those jobs running against live market data. There is no demo product. Current capability is live CoinMarketCap market intelligence only.

A Lens is the teammate. Chief Agent plans. Workflow executes.

## Hierarchy

```
User instruction → ConversationAgent → ClarifiedTask → ChiefAgent → Job + AgentPlan
  → PlanValidator → Workflow
    → AgentRuntime → AgentTask → LensRuntime
      → Crypto Tool Layer → CMC
      → Observation rows → capabilities → Evidence → Verification → Result
      → Response LLM → Conversation
```

Events are only one kind of Result. Policy remains the deterministic evaluator for trigger-only Lenses via `MonitoringService.run_lens`.

Smallest valid execution model: do not force every request into an alert. Compare-now is a task. Watch jobs get a Routine.

## Stack

Django session auth. Templates + HTMX. Celery Beat every 15 minutes. Composer (or heuristic) for intent and explanation only. LLM outputs are schema-validated config. No `eval`, no arbitrary HTTP.

## Auth

- `/signup` `/login` `/logout` `/password-reset/`
- Landing composer stashes `pending_intent` and redirects to signup
- No Enter Demo, no operator account, no `/enter-demo`
- Object access scoped to `request.user`

## Agent OS layer

- Relational `Job` is the live assignment. `job_definition_json` on `LensVersion` stays as the versioned snapshot.
- `AgentPlan` is LLM-facing intent. `Workflow` is the closed execution graph.
- Loop: PLAN → ACT → OBSERVE → VERIFY → REPAIR? → COMPLETE
- Artifact kinds: plan, result, evidence_pack, report, verification, execution_receipt
- Approvals: READ/ANALYZE `not_required`. EXECUTE/PREPARE denied.

## Preserved engine

- `MonitoringService.run_lens` for legacy empty-workflow Lenses
- Policy JSON field names `metrics` / `asset_conditions` / `market_context`
- CMC adapter, scoring, Event receipts, LensVersion pinning
- Telegram connect / test / disconnect

## Tests

Baseline before Agent OS: 52. Agent OS adds isolation, plan validation, loop, evidence, golden BTC receipt, and approval tests.

## Definition of done

Fresh account → give a job → Chief plan → Activate → Watching → Check now → live CMC → Evidence → Verification → Result → execution receipt. No special demo path. Docs distinguish implemented from architectural boundary.
