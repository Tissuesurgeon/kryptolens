# Limitations

- KryptoLens checks the market every 15 minutes. It does not watch a live tape.
- Significance is a deterministic score. The LLM does not decide what matters.
- Composer understands the user message, then Chief Agent plans. Explanation and news briefs are phrased from CMC facts already fetched.
- News uses `GET /v1/content/latest` (News/Headlines). The LLM may only relate those headlines to live quotes. It does not invent prices or stories.
- Content Latest is a Growth+ CoinMarketCap plan endpoint. A 403 fails honestly instead of substituting another news feed.
- Without `CURSOR_API_KEY`, ConversationAgent falls back to a heuristic so the rest of the chain can still run.
- Historical replies are comparable observations, not a prediction.
- DEX, derivatives, RWA, and on-chain tools refuse honestly (403 / not available yet).
- Without `CMC_API_KEY`, Run now fails visibly. The product does not substitute mock candles.
- Fear & Greed is market context, not an asset field.
- `rank_improved` needs a previous rank snapshot. The first run skips that condition instead of failing the whole AND.
- Telegram failures are isolated. The event remains.
- Events store normalized observations and a `CmcCallLog` foreign key, not a full CMC dump.
