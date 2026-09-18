# KryptoLens

Updated: 2026-09-17T01:47:42.965760+00:00

## Identity
Tell KryptoLens what matters. Give it a job. It keeps watch for you.

## Features
- Persistent Lens / Agent (verified)
- Natural-language job compile and conversation (verified)
- Chief Agent planning (verified)
- Closed CMC workflow execution (verified)
- AgentRuntime loop with verification (verified)
- Unattended Beat / routines (verified)
- Live run status (HTMX / JSON) (verified)
- Tool permission boundary (verified)

## Unverified

- Cadence is 15 minutes.
- CMC adapter uses a 60s cache and CmcCallLog; raw JSON never enters the engine.
- Landing composer stashes instruction; no Agent and no CMC job before authentication.
- Scoring is an extracted service; the LLM does not rank events.
- Jobs open an execution trace at /jobs/<id>.
- This iteration is not a multi-agent OS and not a specialist graph; the user sees a single Agent teammate.
