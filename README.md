# KryptoLens

Ask an analyst. It researches live CoinMarketCap data and answers in the same conversation.

KryptoLens is a conversational crypto analyst. You create an **Analyst** (stored as a Lens), ask a question, and it investigates with live market data. A normal question stays one research task. **Keep watching this** turns that task into one Routine. The conversation shows the question, the research, the finding, the evidence, and the verification.

It is not a chatbot, not a market dashboard, not a demo, and not a trading bot. A standing watch checks every **15 minutes**. Quiet markets are a valid result. Missing data is not treated as zero. A coin the user did not name is not filled in as Bitcoin.

Built for the [Build with CMC](https://coinmarketcap.com/api/resources/api-hackathon/) hackathon · **AI Agents and Automation** · `#BuildwithCMC`

## How a question is answered

The user's sentence is interpreted once. After that, nothing else decides what they meant.

```
User message
  → Conversation understanding (LLM JSON → ResearchTask)
  → ResearchContext
  → ResearchPlanner → CapabilityPlan + ResearchPlan
  → Job and Workflow (packed from the plan)
  → AgentRuntime
       PLAN → ACT → OBSERVE → VERIFY → REPAIR if needed → COMPLETE
       LensRuntime → registered CMC tools
  → Observations → deterministic analysis → Finding
  → Evidence → Verification → grounded reply
  → ResearchContext update, in the same conversation
```

`ResearchPlanner` names capabilities and tools. It does not call CoinMarketCap, choose a specialist, or write the reply. `AgentRuntime` executes the stored `CapabilityPlan`. It does not read the sentence again.

Understanding is LLM-first (Grok 4.6 when `CURSOR_API_KEY` is set). Heuristics run only when there is no model, or the model result is missing or invalid. A valid model task is not rewritten by a keyword router.

Capabilities are internal analysis modules: Market, Anomaly, Reaction, Historical, Discovery, and Regime. The user does not pick them. Prices, ranks, and percent changes are calculated in Python from CoinMarketCap observations. The reply may only use figures that came back from that run. An unsupported or inconclusive finding is not stated as a fact.

A follow-up such as “Now add SOL” or “Now do SOL” is read against the current `ResearchContext` (assets, window, and the last task), which lives on the existing Lens JSON. There is no second conversation table.

`ClarifiedTask`, `AgentPlan`, and `ChiefAgent` are compatibility adapters for older stored jobs. They are not a second planner.

A watch such as “when BTC drops 2%, analyze the top 10” waits until that move happens. **Check now** runs the analysis immediately. Bitcoin uses the same trigger step as any other supported asset.

Policy JSON field names stay frozen: `metrics`, `asset_conditions`, `market_context`. The UI may say “Signals.” Storage must not.

## Product path

1. The landing composer stashes the instruction. Nothing is created, and CoinMarketCap is not called, before authentication.
2. **Get Started** (`/signup`) or **Log In** (`/login`). Password reset is Django's built-in flow.
3. After auth, a pending landing instruction creates **your** analyst. Otherwise **Create an Analyst** (name only) on Your Analysts, then send the first message.
4. Ask a question. Understanding produces a `ResearchTask`, the planner selects capabilities, and the reply stays in the thread. If the request is ambiguous, the analyst asks before it fetches.
5. **Keep watching this** creates one Routine from the current task. Close the laptop. Beat ticks every 15 minutes and writes the result into the same conversation. No extra model call. No invented ticks.
6. **Check now**, pause, and resume are messages. **Check now** creates a `LensRun` (`stage=queued`). A chat question runs in the web process. **Check now** and Beat need a Celery worker. The UI polls `LensRun.stage` until `complete` or `error`.
7. The thread shows the question, clarification if needed, the finding, evidence, and verification. A true Event still opens a Receipt. A run opens an execution trace at `/jobs/<id>`.
8. Settings: Connect, test, or disconnect Telegram. Telegram uses the same conversation as the web. A failed send never drops the stored receipt.

A later message that changes a standing watch writes a new `LensVersion` and keeps watching. Old runs stay on the version that produced them.

Workspace status comes from real runs: Idle · Watching · Working · Investigating · Verifying · Waiting for approval · Needs attention · Completed · Paused · Error.

## Workspace

One roster and one transcript. Not a dashboard.

- Left: **Your Analysts** — name, presence, recent activity. **+ New Analyst**. Removing an analyst asks for confirmation in the app.
- Home: who they are, what they watch, and whether they are working. A live CMC strip (BTC / ETH / SOL / TOTAL) sits in the conversation head.
- Selected analyst: name, presence, transcript, composer. Placeholder: **Ask {name}…**.
- A new analyst opens an empty thread. The first screen asks what you would like to research.
- The transcript is a work log: your message, the analyst's reply, one analysis chart when the run has a series, and links only for headlines judged relevant.
- Pause, resume, and check now are messages. There is no specialist picker and no Chat / Routines / Jobs tab.

## Quick start (local)

**Requirements:** Python 3.12+. A [CoinMarketCap Pro API](https://coinmarketcap.com/api/) key for live runs. `CURSOR_API_KEY` if you want Grok to read the message; without it, the heuristic reader is used.

```bash
cp .env.example .env
# set CMC_API_KEY for live listings, and CURSOR_API_KEY for Grok
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py reset_agents  # wipe agents/jobs/runs; keep user accounts
python manage.py runserver
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) → **Get Started** → create an account → **Create an Analyst** → ask a question.

Without `CMC_API_KEY`, a live run persists `stage=error`. The product will not invent market data.

Set `DATABASE_URL` to a Postgres URL (Supabase or Compose). Empty `DATABASE_URL` falls back to local SQLite. Pytest always uses SQLite. **Check now** and the 15-minute Beat schedule need Redis plus Celery:

```bash
# separate terminals
celery -A config worker -l info
celery -A config beat -l info
```

A chat question runs in the web process. **Check now** waits for a worker unless you set `CELERY_TASK_ALWAYS_EAGER=1` for a throwaway local run.

## Docker

```bash
cp .env.example .env
# set CMC_API_KEY, and optional CURSOR_API_KEY / TELEGRAM_BOT_TOKEN
docker compose up --build
```

Compose starts Postgres, Redis, web, worker, beat, and Nginx at [http://localhost:8080](http://localhost:8080).

## Configuration

Copy `.env.example` to `.env`. Never commit secrets.

| Variable | Purpose |
| --- | --- |
| `CMC_API_KEY` | CoinMarketCap Pro API. Required for live research. |
| `CURSOR_API_KEY` | Grok, for understanding the message and writing the briefing. Optional. |
| `LLM_MODEL` | Model id for that provider. Default `grok-4.6`. |
| `LLM_API_KEY` / `LLM_BASE_URL` | Alternate OpenAI-compatible provider, used when `CURSOR_API_KEY` is unset. |
| `TELEGRAM_BOT_TOKEN` | Optional Telegram delivery. |
| `EMAIL_BACKEND` | Password-reset delivery. Defaults to console. |
| `DATABASE_URL` | Postgres URL. Empty = local SQLite. Pytest always uses SQLite. On Supabase, migrate enables RLS on public Django tables so PostgREST cannot read them. |
| `REDIS_URL` | Celery broker. Required for queued Check now and Beat. |
| `EVENT_COOLDOWN_MINUTES` | Dedup window for event fingerprints. Default `60`. |
| `SCORE_HIGH_MIN` / `SCORE_MEDIUM_MIN` | Scoring bands. Defaults `4` / `2`. |
| `SECRET_KEY` / `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` | Django runtime. |
| `CELERY_TASK_ALWAYS_EAGER` | Set `1` only in tests or a throwaway local without a worker. |

With no model key, understanding falls back to the heuristic reader. It does not invent prices.

## CoinMarketCap

Auth header: `X-CMC_PRO_API_KEY`. The key is never logged, never stored on events, and never written into `CmcCallLog`.

| Endpoint | Used when |
| --- | --- |
| `GET /v3/cryptocurrency/listings/latest` | A top-N universe, such as the top 10 by market cap |
| `GET /v3/cryptocurrency/quotes/latest` | Named assets, and a watch trigger |
| `GET /v3/cryptocurrency/quotes/historical` | A window such as the last 30 days, or a year |
| `GET /v3/fear-and-greed/latest` | A market-wide brief |
| `GET /v1/global-metrics/quotes/latest` | A market-wide brief |
| Public headlines page | Headlines for the briefing. The paid `GET /v1/content/latest` endpoint is not used |

Listings and quotes are cached in-process for about 60 seconds. The relevance pass keeps only headlines that match the question. The reply links those, and no others.

Details: [docs/cmc-integration.md](docs/cmc-integration.md). Policy shape: [docs/policy-schema.md](docs/policy-schema.md).

## Tests

```bash
pytest
```

Default tests never call live CoinMarketCap, Grok, or Telegram. They use the heuristic reader. They cover the single research path, follow-ups that keep the current window, a missing asset not becoming Bitcoin, a valid model task beating a heuristic, capability validation, unsupported findings, trigger waits, and Telegram isolate-on-failure.

## What we will not build

Discover, global search, a notification center, portfolio, trading, a specialist picker, extra agent frameworks, CoinGecko, fake events, a frequency picker, or category/map endpoints unless a real research task needs them.

## Limitations

- A standing watch checks every 15 minutes. This is not a real-time tape.
- A “when it drops” watch does not rank the market until the condition is true. **Check now** runs it anyway.
- The model writes the briefing from verified figures. It does not calculate ranks or invent prices.
- Fear & Greed is market-wide context, not an attribute of one asset.
- `rank_improved` needs a previous snapshot. The first run skips that condition instead of failing the whole task.
- Telegram is optional. A missing token or a send failure leaves the result in place.
- Headlines come from the public CoinMarketCap headlines page. The paid content API is not available on this key.

Full list: [docs/limitations.md](docs/limitations.md).

## Documentation

| Doc | Contents |
| --- | --- |
| [PLAN.md](PLAN.md) | Architecture and what is in this build |
| [docs/architecture.md](docs/architecture.md) | Research path, run stages, deployment |
| [docs/policy-schema.md](docs/policy-schema.md) | Frozen policy JSON and near-match shape |
| [docs/cmc-integration.md](docs/cmc-integration.md) | Named endpoints, observation model, evidence |
| [docs/demo.md](docs/demo.md) | Fresh-account walkthrough |
| [docs/demo-script.md](docs/demo-script.md) | Judge walkthrough |
| [docs/limitations.md](docs/limitations.md) | Honest constraints |
| [docs/submission.md](docs/submission.md) | Hackathon submission notes |
| [docs/ui-design-skills.md](docs/ui-design-skills.md) | Hierarchy, proximity, contrast |
| [DESIGN.md](DESIGN.md) | Sage field, cream paper, bark outlines |
