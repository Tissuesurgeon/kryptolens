# KryptoLens

Updated: 2026-09-29T04:24:14.917414+00:00

## Identity
A conversational crypto analyst: create an Analyst (stored as a Lens), ask a question, and it researches live CoinMarketCap data in the same conversation.

## Features
- Persistent Lens / Analyst (verified)
- Conversational job compiler (verified)
- LLM-first request understanding (verified)
- Research planner (verified)
- Agent runtime loop (verified)
- Policy evaluation and scoring (verified)
- CoinMarketCap market data (verified)
- Activate, pause, and run-now controls (verified)
- Scheduled Beat / Celery routines (inferred)

## Unverified

- Standing watches check every 15 minutes.
- Understanding uses Grok 4.6 when CURSOR_API_KEY is set; heuristics only if the model is missing or invalid.
- Landing composer stashes the instruction and does not create a Lens or call CMC before authentication.
- UI polls LensRun.stage until complete or error; Check now and Beat need a Celery worker while a chat question runs in the web process.
