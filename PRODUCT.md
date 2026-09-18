# KryptoLens

Tell KryptoLens what you want. A Lens keeps watch for you.

KryptoLens is a persistent crypto intelligence workspace. Users create a **Lens**, talk to it in natural language, and leave jobs running against live CoinMarketCap data.

The user does not pick capabilities or specialists. They create a Lens, tell it what they want, clarify when asked, and continue the same conversation.

```
Create a Lens.
Tell it what you want.
Clarify when asked.
Let it investigate.
Continue the conversation.
```

## Platform

web

## Register

product

## Core loop

```
User
  → Lens conversation
  → Understanding Agent (LLM JSON)
  → ClarifiedTask
  → Chief Agent
  → CapabilityPlan
  → Capabilities + CMC tools
  → Workflow
  → Deterministic analysis
  → Verification
  → Response
  → Same Lens thread
```

Create a Lens (name only) → open an empty conversation → send the first message. A Routine is the standing watch that follows from that message. Unattended Beat writes back into the same conversation. Jobs are LensRuns. Market numbers come from live CoinMarketCap only. `IntelligencePolicy` is a compiled artifact, not the user mental model.

## Core concepts

- **Lens** — persistent crypto teammate
- **Job** — a run of work (`LensRun`) plus a standing assignment snapshot
- **ClarifiedTask** — what the user actually asked for
- **CapabilityPlan** — Chief Agent's validated capabilities, tools, and workflow
- **Workflow** — how approved operations run (`get_quotes`, `get_market_listings`, `get_content`, `calculate`, `sort`, `present`)
- **Routine** — when it should work; Pause is per-routine
- **Tools** — CoinMarketCap read/analyze tools, including Content Latest for headlines
- **Evidence / Verification** — compact claims and checkmarks in the same thread
- **Capabilities** — internal Market / Anomaly / Reaction / Historical / Discovery / Regime modules selected by the Chief Agent
- **Result** — ranked table, comparison, summary, news brief, event, no-result, or error
- **Execution receipt** — what triggered, what ran, evidence, verification

## Internal capabilities

These are not bots the user manages:

| Capability | What the Chief uses it for |
| --- | --- |
| Market | Live quotes, listings, summaries |
| Anomaly | Unusual activity against a stated definition |
| Reaction | How the universe moves when a trigger asset moves |
| Historical | Comparable prior observations, not predictions |
| Discovery | Attention, gainers, new listings |
| Regime | Breadth, dominance, Fear & Greed context |

## Capability

| Capability | Status |
| --- | --- |
| Understanding Agent | Implemented, LLM-first |
| Chief Agent / CapabilityPlan | Implemented |
| Market / Anomaly / Reaction / Historical / Discovery / Regime | Implemented |
| CoinMarketCap | Implemented (live listings, quotes, Fear & Greed, global metrics, Content Latest news) |
| Evidence / Verification | Implemented |
| Approvals | Foundation only |
| Onchain / DeFi / Risk / Security | Architectural boundary |
| News | Implemented via CMC Content Latest + quotes |
| Wallet / Execution | Future |

## Who it is for

Someone who can name a crypto-market job in language and wants a teammate that stays on it — not a dashboard they have to configure.

## Scene

Night desk. A researcher creates Crypto Scout, tells it what to watch, leaves it on live CoinMarketCap, and comes back to a verified result with evidence.

## Voice

Direct. Specific. Tell → Clarify → Watch → Act → Return. Never claims real-time or literal continuous observation. Monitoring happens every 15 minutes. Never calls itself a demo. Never invents market numbers.

## Surfaces

Landing (Get Started / Log In) → signup or login → Your Lenses → Create a Lens → empty conversation → Ask KryptoLens…. Pause, resume, and check now are messages. Live CMC strip on the workspace. Settings / Log Out.

## Out of scope

- Trading, charts, wallets, third-party news APIs, fake demo mode, specialist pickers, LLM scoring or invented ticks.
