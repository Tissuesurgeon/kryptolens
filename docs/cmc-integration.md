# CoinMarketCap integration

KryptoLens uses the CoinMarketCap Pro API as the only market data source in v1.

## Auth

Header: `X-CMC_PRO_API_KEY`. The key is never logged, never written to `CmcCallLog`, and never stored on Event.

## Named endpoints

| Endpoint | When |
|---|---|
| `/v3/cryptocurrency/listings/latest` | Universe type `listings` (demo: top 100 by market cap) |
| `/v3/cryptocurrency/quotes/latest` | Universe type `symbols` (named assets such as BTC) |
| `/v3/fear-and-greed/latest` | Policy includes Fear & Greed as **market context** |
| `/v1/global-metrics/quotes/latest` | Only when policy context needs global market fields (`btc_dominance`, `eth_dominance`, `total_market_cap`) |

Category and map endpoints are reserved for a later policy that actually needs them.

## Observation Model

Raw JSON never enters the policy engine.

```
CMC JSON → Normalizer → MarketObservation / MarketContext → Engine
```

Fear & Greed is market-wide context. It is not an attribute of SOL or any other asset.

## Evidence

Each monitoring run writes `CmcCallLog` rows: endpoint, redacted params, status, `credit_count`, field list, and a short response excerpt. The Event Receipt **View API evidence** control opens a `<dialog>` reconstructed via `Event → CmcCallLog`.

## Cache and caps

Listings and quotes are cached in-process for ~60 seconds. Universe size is capped at the policy limit (demo: 100).

## Failures

Missing keys, timeouts, HTTP 4xx/5xx, and 429 raise `CMCError`. Run now surfaces the error on the lens. Beat records it on `LensRun` and continues with the next lens.
