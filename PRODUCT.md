# KryptoLens

Tell KryptoLens what matters. Give it a job. It keeps watch for you.

KryptoLens is a persistent crypto intelligence workspace where users create **Agents** (the UI name for a Lens), talk to them in natural language, give them crypto-market jobs, and leave those jobs running against live market data.

An **Agent** is the only visible teammate. Planning logic stays inside the Lens. The user sees **Agents**. This iteration is not a multi-agent OS and not a specialist graph.

## Platform

web

## Register

product

## Core loop

chat → ConversationAgent → ClarifiedTask → Chief Agent plan → live CMC → verify → Response LLM.

Create Agent → named teammate → chat a job → work starts in the thread. A Routine is the standing watch that follows from that message, not a setup wizard. Unattended Beat writes back into the same conversation. Jobs are LensRuns. Market numbers come from live CoinMarketCap only.

## Core concepts

- **Agent** — UI name for a Lens: persistent crypto teammate
- **Job** — a run of work (`LensRun`) plus a standing assignment snapshot
- **AgentPlan** — what the agent intends (schema-validated). Does not call CMC.
- **Workflow** — how approved operations run (`get_quotes`, `get_market_listings`, `get_content`, `calculate`, `sort`, `present`)
- **Routine** — when it should work; Pause is per-routine
- **Tools** — CoinMarketCap read/analyze tools in this build, including Content Latest for headlines
- **Evidence / Verification** — compact claims and checkmarks in the same thread
- **Capabilities** — hidden Market / Anomaly / Reaction / Historical / Discovery / Regime modules
- **Result** — ranked table, comparison, summary, news brief, event, no-result, or error
- **Execution receipt** — what triggered, what ran, evidence, verification
- **Event** — one kind of Result: a trigger-fired condition

## Capability

| Capability | Status |
| --- | --- |
| Chief Agent | Implemented |
| Market capability | Implemented |
| CoinMarketCap | Implemented (live listings, quotes, Fear & Greed, global metrics, Content Latest news) |
| Research | Implemented, limited to CMC |
| Evidence / Verification | Implemented |
| Approvals | Foundation only |
| Onchain / DeFi / Risk / Security | Architectural boundary |
| News | Implemented via CMC Content Latest + quotes |
| Wallet / Execution | Future |

## Who it is for

Someone who can name a crypto-market job in language and wants a teammate that stays on it — not a dashboard they have to configure.

## Scene

Night desk. A researcher gives an Agent a job, leaves it watching live CoinMarketCap, and comes back to a verified result with evidence.

## Voice

Direct. Specific. Tell → Define → Watch → Act → Return. Never claims real-time or literal continuous observation. Monitoring happens every 15 minutes. Never calls itself a demo. Never claims unsupported specialists.

## Surfaces

Landing (Get Started / Log In) → signup or login → Agent home → Create Agent → chat a job (Ask {name}, You asked / KryptoLens assumed / I'll do, watching, CMC activity). Pause and check now are messages. Live CMC strip on the workspace. Settings / Log Out.

## Out of scope

- Trading, charts, wallets, third-party news APIs, fake demo mode, fake specialist agents, LLM scoring or invented ticks.
