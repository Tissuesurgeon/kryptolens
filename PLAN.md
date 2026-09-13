# KryptoLens build plan

Approved architecture for the Build with CMC hackathon (AI Agents and Automation, 9–30 Sep 2026).

## What it is

KryptoLens compiles human information intent into a continuously executable Intelligence Policy. Externally: an intent-driven crypto intelligence system, not a chatbot or dashboard. It monitors on your behalf every 15 minutes.

## Hierarchy

```
Human intent → Intent compilation → Intelligence Policy → QueryPlan
→ CMC Adapter → Observation Model → Detection → Scoring → Explanation
→ Event Receipt → Web + Telegram
```

Policy is the core domain object. A Lens is the user-facing configuration. Only two agents exist: Intent Agent and Explanation Agent.

## Stack

Django + templates + HTMX + CSS variables. Persistent-agent workspace (roster + conversation artifacts). Composer (or heuristic fallback) for intent and explanation only. Deterministic scoring. One `MonitoringService` shared by Celery Beat and async Run now.

## Spec-close status

### Done

- Baseline recorded: 26 tests green before edits
- M0 spike left in place (`spikes/m0_chain.py`, `Dockerfile.m0`). Docker re-run skipped: no `CMC_API_KEY` / `CURSOR_API_KEY` in the environment. Heuristic compiler remains the honest fallback.
- `LensRun` artifacts: `stage`, `summary_json`, `near_matches_json` (frozen near-match shape)
- Scoring extracted to `apps/intelligence/scoring.py`; `evaluate_policy` calls it
- Demo flags `is_demo_scenario` / `is_example` removed; cleanup-delete in `ensure_workspace_user` removed
- Compile report: `you_asked`, `assumptions`, `clarification`, `confidence` (interpretation only)
- Optional `get_global_metrics()` only when policy context needs global market fields
- Persistent workspace shell + conversation artifacts
- Landing composer uses the same compiler; persist only after **Enter Demo**
- Async Run now: create run (`queued`), queue Celery `run_lens`, return `run_id`; HTMX polls stage
- Five-block receipt + CMC evidence `<dialog>`
- NL edit → policy diff artifact → new `LensVersion`
- Telegram connect / test / disconnect
- Docs: architecture, agent-design, policy-schema, demo; CMC notes refreshed

### Issues

- Live M0 Docker hop was not re-verified in this environment (keys absent)

### Documented deviations

- The repo was already a working modular monolith. Spec-close extended services; it did not scaffold from zero.
- Policy JSON field names remain `metrics` / `asset_conditions` / `market_context`.
- `run_lens` was extended (stages, summary, near matches, optional existing run), not rewritten.
- Landing **Enter Demo** is operator-account login only. No seeded events.

## Definition of done

Enter Demo → compile intent → Policy v1 → Activate → async Run now → live listings + Fear & Greed → scored Event → Receipt + API evidence dialog → optional Telegram.

No mock market data on the demo path. Secrets never committed. `#BuildwithCMC`.
