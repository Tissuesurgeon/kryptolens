# Limitations

- KryptoLens checks the market every 15 minutes. It does not watch a live tape.
- Significance is a deterministic score. The LLM does not decide what matters.
- Composer is used only to compile intent and to phrase an explanation from facts already scored.
- Without `CURSOR_API_KEY`, intent compilation uses a heuristic provider so the rest of the chain can still run.
- Without `CMC_API_KEY`, Run now fails visibly. The product does not substitute mock candles.
- Fear & Greed is market context, not an asset field.
- `rank_improved` needs a previous rank snapshot. The first run skips that condition instead of failing the whole AND.
- Telegram failures are isolated. The event remains.
- Events store normalized observations and a `CmcCallLog` foreign key, not a full CMC dump.
