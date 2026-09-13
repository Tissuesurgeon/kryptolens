# KryptoLens

See what matters in crypto.

KryptoLens is an intent-driven crypto intelligence system. You name a market condition in language. It compiles that into a versioned **Intelligence Policy**, fetches the minimum live [CoinMarketCap](https://coinmarketcap.com/api/) data required, evaluates every asset deterministically, and — when something qualifies — writes an Event Receipt you can inspect or send to Telegram.

It is not a chatbot, not a market dashboard, and not a trading bot. Cadence is **15 minutes**. Quiet markets are a valid result: zero events is a successful scan.

Built for the [Build with CMC](https://coinmarketcap.com/api/resources/api-hackathon/) hackathon · **AI Agents and Automation** · `#BuildwithCMC`

## How it works

```
Human intent
  → Intent Agent (NL → IntelligencePolicy)
  → Query plan (minimum CMC endpoints)
  → CMC adapter (live listings / quotes / Fear & Greed / optional global metrics)
  → Normalized observations
  → Policy engine + scoring
  → Event (if the policy fires)
  → Explanation Agent (facts → brief)
  → Event Receipt (web + optional Telegram)
```

Only two agents exist. Query planning, CMC, detection, scoring, and Telegram are ordinary software.

| Piece | Role |
| --- | --- |
| Intent Agent | Compiles language into `IntelligencePolicy` JSON and an asked-vs-assumed report |
| Explanation Agent | Writes a short brief from already-scored facts |
| Query planner | Chooses listings vs quotes, Fear & Greed, and global metrics only when the policy needs them |
| CMC adapter | Auth, 60s cache, `CmcCallLog`. Raw JSON never enters the engine |
| Policy engine | Deterministic `evaluate_policy` |
| Scoring | Extracted service (`apps/intelligence/scoring.py`). The LLM does not rank events |
| `MonitoringService.run_lens` | One path for Celery Beat and **Run now** |

**You asked / KryptoLens assumed** is interpretation of the compile, never a market prediction. `confidence` on the compile report is how sure the compiler is that it understood the request.

Policy JSON field names are frozen: `metrics`, `asset_conditions`, `market_context`. UI copy may say “Signals.” Storage must not.

## Product path

1. Landing composer (optional) — same compiler as the app. Preview is session-only. **No anonymous database rows.**
2. **Enter Demo** (`GET /enter-demo`; `/start` is an alias) — logs in the single operator account (`APP_EMAIL` / `APP_PASSWORD`). Nothing is seeded.
3. If a landing intent was previewed, a Lens is created after auth. Otherwise compile from **Ask KryptoLens…**.
4. Review asked vs assumed and the policy card. **Activate**.
5. **Run now** creates a `LensRun` (`stage=queued`), queues the same Celery `run_lens` task, and returns `run_id` immediately. HTMX polls `LensRun.stage` until `complete` or `error`.
6. Open an Event Receipt. **View API evidence** is a dialog: endpoint, redacted params, fields used, sanitized excerpt.
7. Settings: Connect / test / disconnect Telegram. A failed send never drops the stored receipt.

Natural-language edit previews a policy diff, then **Apply** writes a new `LensVersion`. Old events stay on the version that produced them.

Workspace status is derived from real runs: Watching / Checking / Scan complete / Degraded / Paused.

## Workspace

Persistent-agent layout, not a chat transcript.

- Left: **Your Lenses**, New Lens, Settings
- Main: structured plates — asked/assumed, policy, live scan, scan summary, near matches, event rows, receipt
- Bottom: **Ask KryptoLens…** (create on home, revise on a lens)

Near-match objects have a frozen shape (`symbol`, `name`, `actuals`, `conditions[].passed`). Templates only render those fields.

## Quick start (local)

**Requirements:** Python 3.12+, a [CoinMarketCap Pro API](https://coinmarketcap.com/api/) key for live runs.

```bash
cp .env.example .env
# set CMC_API_KEY for live listings
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) → **Enter Demo** → compile a lens → **Activate** → **Run now**.

Without `CMC_API_KEY`, Run now persists `stage=error`. The product will not invent market data.

Local SQLite is used when `DATABASE_URL` is empty. **Run now** and the 15-minute Beat schedule need Redis plus Celery:

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
| `APP_EMAIL` / `APP_PASSWORD` | Single operator account. Defaults are in `.env.example`. |
| `DATABASE_URL` | Empty = local SQLite. Compose sets Postgres. |
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
| [docs/demo.md](docs/demo.md) | Enter Demo walkthrough |
| [docs/cmc-integration.md](docs/cmc-integration.md) | Named endpoints, observation model, evidence |
| [docs/demo-script.md](docs/demo-script.md) | Judge walkthrough |
| [docs/limitations.md](docs/limitations.md) | Honest constraints |
| [docs/submission.md](docs/submission.md) | Hackathon submission notes |
| [docs/ui-design-skills.md](docs/ui-design-skills.md) | Saved UI skills (hierarchy, proximity, contrast) |
| [DESIGN.md](DESIGN.md) | Night-desk visual system |
