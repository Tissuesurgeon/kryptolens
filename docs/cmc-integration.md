# CoinMarketCap integration

KryptoLens uses the CoinMarketCap Pro API as the only market data source in v1.

## Auth

Header: `X-CMC_PRO_API_KEY`. The key is never logged, never written to `CmcCallLog`, and never stored on Event.

## Named endpoints

| Endpoint | When |
|---|---|
| `/v3/cryptocurrency/listings/latest` | Universe type `listings` (demo: top 100 by market cap) |
| `/v3/cryptocurrency/quotes/latest` | Universe type `symbols` (named assets such as BTC) |
| `/v2/cryptocurrency/quotes/historical` | Historical compare windows. Honest 403 if not on the key. |
| `/v2/cryptocurrency/ohlcv/historical` | OHLCV windows. Honest 403 if not on the key. |
| `/v1/cryptocurrency/trending/latest` | Discovery. Honest 403 on Startup if not entitled. |
| `/v1/cryptocurrency/trending/gainers-losers` | Discovery. Honest 403 if not entitled. |
| `/v1/cryptocurrency/listings/new` | New listings. Honest 403 if not entitled. |
| `/v1/cryptocurrency/categories` | Category context. Honest 403 if not entitled. |
| `/v2/cryptocurrency/price-performance-stats/latest` | Optional market stats. Honest 403 if not entitled. |
| `/v3/fear-and-greed/latest` | Policy includes Fear & Greed as **market context** |
| `/v1/global-metrics/quotes/latest` | Only when policy context needs global market fields (`btc_dominance`, `eth_dominance`, `total_market_cap`) |
| `/v1/content/latest` | News questions: CMC News/Headlines (and optional Alexandria). Growth+ plans. |
| `/v3/altcoin-season/latest` | Regime. Stubbed with honest 403 until the live key returns 200. |
| `/v3/index/quotes/latest` | CMC20 / CMC100. Report “index not on this plan” unless 200. |

DEX, derivatives, and RWA tools stay disabled (`DISABLED_SLOTS`) until Startup-tier entitlement is verified.

## Observation Model

Raw JSON never enters the policy engine.

Raw JSON never enters the policy engine. Each run persists `lenses.Observation` rows (`asset_id`, `symbol`, `observed_at`, `fields_json`, `source_endpoint`). Evidence references those ids.

```
CMC JSON → Normalizer → MarketObservation / MarketContext → Observation rows → Capabilities
```

Fear & Greed is market-wide context. It is not an attribute of SOL or any other asset.

## Evidence

Each monitoring run writes `CmcCallLog` rows: endpoint, redacted params, status, `credit_count`, field list, and a short response excerpt. The Event Receipt **View API evidence** control opens a `<dialog>` reconstructed via `Event → CmcCallLog`.

## Cache and caps

Listings and quotes are cached in-process for ~60 seconds. Universe size is capped at the policy limit (demo: 100).

## Failures

Missing keys, timeouts, HTTP 4xx/5xx, and 429 raise `CMCError`. Run now surfaces the error on the lens. Beat records it on `LensRun` and continues with the next lens.
