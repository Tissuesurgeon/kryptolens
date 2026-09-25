# KryptoLens

Ask an analyst. It researches live CoinMarketCap data in one conversation.

KryptoLens is a conversational crypto analyst. Users create an **Analyst**, ask a question, and get a finding with evidence. The stored object is still a Lens.

The user does not pick capabilities or specialists. They create an analyst, ask what they want to research, clarify when asked, and continue the same conversation.

```
Create an Analyst.
Ask what you want to research.
Clarify when asked.
Read the finding and the evidence.
Keep watching only when you say so.
```

## Platform

web

## Register

product

## Core loop

```
User message
  → Understanding
  → ResearchTask + ResearchContext
  → ResearchPlanner
  → ResearchPlan + CapabilityPlan
  → Existing runtime
  → Finding, evidence, verification
  → Same analyst conversation
```

Create an Analyst (name only) → open an empty conversation → ask the first question. A Routine is created only from “keep watching this”. Unattended Beat writes later findings into the same conversation. Jobs are LensRuns. Market numbers come from live CoinMarketCap only. `IntelligencePolicy` is a compiled artifact, not the user mental model.

## Core concepts

- **Analyst** — the conversation the user sees. Stored as a Lens
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

Landing (Create an Analyst / Log In) → signup or login → Your Analysts → Create an Analyst → empty conversation → Ask {name}…. Pause, resume, and check now are messages. Live CMC strip on the workspace. Settings / Log Out.

## Out of scope

- Trading, charts, wallets, third-party news APIs, fake demo mode, specialist pickers, LLM scoring or invented ticks.
