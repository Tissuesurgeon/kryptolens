# Demo

Operator-only workspace. No seeded lenses or events.

1. Open the landing page. Optionally preview a compile in the composer (**You asked** / **KryptoLens assumed**). Nothing is written to the database yet.
2. Click **Enter Demo** (`GET /enter-demo`; `/start` is an alias). This logs in the operator account from `APP_EMAIL` / `APP_PASSWORD`.
3. If a landing intent was previewed, KryptoLens now persists the Lens. Otherwise compile from **Ask KryptoLens…**.
4. Review the conversation artifacts. **Activate**.
5. **Run now** returns immediately with a `run_id`. HTMX polls `LensRun.stage` until `complete` or `error`.
6. Open an Event Receipt. **View API evidence** opens a dialog (endpoint, redacted params, fields used, sanitized excerpt).
7. Settings: Connect / test / disconnect Telegram.

Cadence is 15 minutes. Quiet markets (0 events, N near matches) are a valid result.

M0 spike: `spikes/m0_chain.py` + `Dockerfile.m0`. Re-run in Docker only when `CMC_API_KEY` and a compiler key are present. Without keys, CMC fails honestly and the heuristic compiler still produces policy JSON.
