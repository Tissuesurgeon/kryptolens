# KryptoLens

Tell KryptoLens what matters. Give it a job. It keeps watch for you.

KryptoLens is a persistent crypto intelligence workspace where users create a **Lens**, tell it what they want in natural language, and leave those jobs running against live market data. A **Routine** starts work without another prompt. Celery Beat runs unattended through **AgentRuntime** → LensRuntime → CMC. The conversation is a structured work log: Plan → Evidence → Verification → Result.

It is not a chatbot, not a market dashboard, not a demo, and not a trading bot. Cadence is **15 minutes**. Quiet markets are a valid result.

Built for the [Build with CMC](https://coinmarketcap.com/api/resources/api-hackathon/) hackathon · **AI Agents and Automation** · `#BuildwithCMC`

## How it works

```
User
  → Lens conversation
  → Understanding Agent (LLM JSON)
  → ClarifiedTask
  → Chief Agent → CapabilityPlan
  → Capabilities + registered CMC tools
  → Workflow
  → Deterministic analysis
  → Verification
  → Response Agent
  → Same Lens thread
```

Chief Agent does not call CMC. Capabilities declare tools; `dispatch_cmc` executes. On-chain, DEX, derivatives, and RWA are registry stubs with honest 403. News uses CoinMarketCap Content Latest plus quotes.

| Piece | Status | Role |
| --- | --- | --- |
| Understanding Agent | Implemented | LLM-first ClarifiedTask; heuristics are fallback only |
| ClarifiedTask | Implemented | What the user asked; source of truth for compile |
| Chief Agent / CapabilityPlan | Implemented | Selects one or more capabilities and validated tools. Does not call CMC |
| Internal capabilities | Implemented | Market, Anomaly, Reaction, Historical, Discovery, Regime — not user-managed bots |
| Evidence / Verification | Implemented | Compact claims and checkmarks in the thread |
| Approvals | Foundation only | READ/ANALYZE not required; EXECUTE denied |
| Onchain / DEX / Derivatives / RWA | Boundary | Honest refusal, not on Startup |
| News | Implemented, CMC Content Latest | Headlines related to live quotes |
| Wallet / Execution | Future | Not available yet |
| CMC adapter | Implemented | Auth, 60s cache, `CmcCallLog`. Raw JSON never enters the engine |
| `AgentRuntime` / `LensRuntime` | Implemented | Chat, Check now, and Beat share one path |

**You asked / KryptoLens assumed** is the LLM's interpretation of the message, never a market prediction. `confidence` is how sure that understanding is. The Chief Agent plans from it and does not call CMC.

Policy JSON field names are frozen: `metrics`, `asset_conditions`, `market_context`. UI copy may say “Signals.” Storage must not.

## Product path

1. Landing composer stashes the instruction. **No Agent and no CMC job before authentication.**
2. **Get Started** (`/signup`) or **Log In** (`/login`). Password reset is Django's built-in flow.
3. After auth, a pending landing instruction creates **your** Lens. Otherwise **Create a Lens** (name only) on Your Lenses, then send the first message.
4. Chat a job. The LLM understands it (**You asked** / **KryptoLens assumed** / I'll do), Chief Agent plans, and work starts in the thread. A Routine is standing watch — not a setup form.
5. Close the laptop. Beat ticks every 15 minutes, calls the same Celery `run_lens` task as **Check now** (`AgentRuntime` → `LensRuntime` → live CMC), and writes the result into the conversation. No extra LLM. No invented ticks.
6. **Check now** creates a `LensRun` (`stage=queued`) and returns `run_id` immediately. HTMX polls `LensRun.stage` until `complete` or `error`. CMC activity cards in the transcript show real endpoints, status, and elapsed_ms.
7. Conversation artifacts appear in order: Plan → Evidence → Verification → Result → Execution receipt. True Events still open a Receipt. Jobs open an execution trace at `/jobs/<id>`.
8. Settings: Connect / test / disconnect Telegram. Telegram inbound uses the same conversation as the web. A failed send never drops the stored receipt.

A later message that changes a standing job writes a new `LensVersion` and keeps watching. Old runs stay on the version that produced them.

Workspace status is derived from real runs: Idle · Watching · Working · Investigating · Verifying · Waiting for approval · Needs attention · Completed · Paused · Error.

## Workspace

Agent Home and one transcript — not a dashboard.

- Left: **Your Lenses** — name, status, recent activity. **+ New Lens**.
- Home: Who → State → Activity. Live CMC strip (BTC / ETH / SOL / TOTAL).
- Selected Lens: name + presence (Watching / Working / Idle), transcript, composer. Pause / resume / check now are messages.
- Transcript: work log — messages, clarification, compact work preview, Plan → Evidence → Verification → Result
- Bottom: **Ask KryptoLens…**. A new Lens opens an empty conversation. The user sends the first message.

Near-match objects have a frozen shape (`symbol`, `name`, `actuals`, `conditions[].passed`). Templates only render those fields.

## Quick start (local)

**Requirements:** Python 3.12+, a [CoinMarketCap Pro API](https://coinmarketcap.com/api/) key for live runs.

```bash
cp .env.example .env
# set CMC_API_KEY for live listings
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py reset_agents  # wipe agents/jobs/runs; keep user accounts
python manage.py runserver
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) → **Get Started** → create an account → give a Lens a job → **Activate** → **Check now**.

Without `CMC_API_KEY`, Run now persists `stage=error`. The product will not invent market data.

Set `DATABASE_URL` to a Postgres URL (Supabase or Compose). Empty `DATABASE_URL` falls back to local SQLite. Pytest always uses SQLite. **Run now** and the 15-minute Beat schedule need Redis plus Celery:

```bash
# separate terminals
celery -A config worker -l info
celery -A config beat -l info
```

Without a worker, the HTTP handler still creates the queued run and returns `run_id`. The scan does not execute until a worker picks it up (or you call `MonitoringService.run_lens` directly).

## Docker

```bash
cp .env.example .env
# set CMC_API_KEY (and optional CURSOR_API_KEY / TELEGRAM_BOT_TOKEN)
docker compose up --build
```

Compose starts Postgres, Redis, web, worker, beat, and Nginx at [http://localhost:8080](http://localhost:8080).

M0 spike (prompt → policy → live CMC → evaluate) is already in the tree: `spikes/m0_chain.py` and `Dockerfile.m0`. It does not fall back to fixture market data. Re-run it in Docker only when keys are present.

## Configuration

Copy `.env.example` to `.env`. Never commit secrets.

| Variable | Purpose |
| --- | --- |
| `CMC_API_KEY` | CoinMarketCap Pro API. Required for live monitoring. |
| `CURSOR_API_KEY` | Composer 2.5 for intent and explanation. Optional. |
| `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL` | Alternate OpenAI-compatible provider. Optional. |
| `TELEGRAM_BOT_TOKEN` | Optional Event → Telegram delivery. |
| `EMAIL_BACKEND` | Password-reset delivery. Defaults to console. |
| `DATABASE_URL` | Postgres URL. Empty = local SQLite. Pytest always uses SQLite. On Supabase, migrate enables RLS on public Django tables so PostgREST cannot read them. |
| `REDIS_URL` | Celery broker. Required for queued Run now and Beat. |
| `EVENT_COOLDOWN_MINUTES` | Dedup window for event fingerprints. Default `60`. |
| `SCORE_HIGH_MIN` / `SCORE_MEDIUM_MIN` | Scoring bands. Defaults `4` / `2`. |
| `SECRET_KEY` / `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS` | Django runtime. |
| `CELERY_TASK_ALWAYS_EAGER` | Set `1` only in tests or a throwaway local without a worker. |

If no LLM key is set, `HeuristicCompiler` still produces a valid policy so the rest of the product can run.

## CoinMarketCap

Auth header: `X-CMC_PRO_API_KEY`. The key is never logged, never stored on events, and never written into `CmcCallLog`.

| Endpoint | Used when |
| --- | --- |
| `GET /v3/cryptocurrency/listings/latest` | Universe is top-N listings |
| `GET /v3/cryptocurrency/quotes/latest` | Universe is named symbols (e.g. BTC) |
| `GET /v3/fear-and-greed/latest` | Policy includes Fear & Greed as **market context** |
| `GET /v1/global-metrics/quotes/latest` | Only when policy context needs global market fields |
| `GET /v1/content/latest` | News questions: CMC News/Headlines, then live quotes for tagged assets |

Listings and quotes are cached in-process for about 60 seconds. Events store normalized observations plus a foreign key to the call log — not a full CMC dump.

Details: [docs/cmc-integration.md](docs/cmc-integration.md). Policy shape: [docs/policy-schema.md](docs/policy-schema.md).

## Tests

```bash
pytest
```

Default tests never call live CMC, Composer, or Telegram. They cover compile asked-vs-assumed, near-match shape, zero-event `ok`, CMC error → `stage=error`, async Run now returning `run_id`, versioned receipts, and Telegram isolate-on-failure.

`python spikes/m0_chain.py` is the live hop. It fails honestly without keys.

Judge walkthrough: [docs/demo-script.md](docs/demo-script.md).

## What we will not build

Discover, global search, a notification center, portfolio, trading, extra agents, CoinGecko, fake events, a frequency picker, or category/map endpoints unless a real policy needs them.

## Limitations

- Cadence is 15 minutes. This is not a real-time tape.
- Significance is a numeric score with reasons. The LLM does not rank events.
- Composer is used only to compile intent and to phrase an explanation from facts already scored.
- Fear & Greed is market-wide context, not an attribute of an asset.
- `rank_improved` needs a previous snapshot; the first run skips that condition instead of failing the whole policy.
- Telegram is optional. A missing token or a send failure leaves the event in place.

Full list: [docs/limitations.md](docs/limitations.md).

## Documentation

| Doc | Contents |
| --- | --- |
| [PLAN.md](PLAN.md) | Architecture and spec-close status |
| [docs/architecture.md](docs/architecture.md) | Locked chain, run stages, deployment |
| [docs/agent-design.md](docs/agent-design.md) | Two agents; asked vs assumed |
| [docs/policy-schema.md](docs/policy-schema.md) | Frozen policy JSON and near-match shape |
| [docs/demo.md](docs/demo.md) | Fresh-account walkthrough |
| [docs/cmc-integration.md](docs/cmc-integration.md) | Named endpoints, observation model, evidence |
| [docs/demo-script.md](docs/demo-script.md) | Judge walkthrough |
| [docs/limitations.md](docs/limitations.md) | Honest constraints |
| [docs/submission.md](docs/submission.md) | Hackathon submission notes |
| [docs/ui-design-skills.md](docs/ui-design-skills.md) | Saved UI skills (hierarchy, proximity, contrast) |
| [DESIGN.md](DESIGN.md) | Night-desk visual system |
