# Agent design

KryptoLens has two agents. Query planning, CMC, detection, scoring, and Telegram are not agents.

## Intent Agent

Compiles natural language into `IntelligencePolicy` JSON (`apps/intelligence/compiler.py`).

The compile path returns interpretation metadata — never a market prediction:

```json
{
  "policy": {},
  "you_asked": ["top 100 altcoins", "unusual price activity", "unusual volume activity"],
  "assumptions": ["altcoins excludes stablecoins"],
  "clarification": null,
  "confidence": 0.94
}
```

`confidence` is how sure the compiler is that it understood the request. The UI labels this **You asked** / **KryptoLens assumed**. It must never be shown as “the market will move.”

Composer (or another chat-completions provider) is preferred. `HeuristicCompiler` is the offline fallback. Policy field names are not renamed for the fallback.

## Explanation Agent

Writes a short brief from already-scored facts (`apps/intelligence/explain.py`). If the model is unavailable, `fallback_explanation` is used. The model does not change the score, severity, or promote/suppress decision.

## What is not an agent

- Query planner — selects CMC endpoints from the policy
- CMC adapter — live HTTP + 60s cache
- Policy engine + scoring — deterministic
- Telegram — delivery after a receipt exists
