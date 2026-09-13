from __future__ import annotations

from datetime import datetime, timezone

from apps.intelligence.observations import MarketContext, MarketObservation

STABLECOIN_SYMBOLS = {
    "USDT",
    "USDC",
    "BUSD",
    "DAI",
    "TUSD",
    "USDE",
    "FDUSD",
    "USDP",
    "GUSD",
    "PYUSD",
}


def quote_usd(item: dict) -> dict:
    quote = item.get("quote") or {}
    return quote.get("USD") or next(iter(quote.values()), {}) or {}


def normalize_listing(item: dict, previous_ranks: dict[int, int] | None = None) -> MarketObservation:
    usd = quote_usd(item)
    asset_id = int(item.get("id") or 0)
    previous = None
    if previous_ranks and asset_id in previous_ranks:
        previous = previous_ranks[asset_id]
    observed = item.get("last_updated") or usd.get("last_updated")
    observed_at = datetime.now(timezone.utc)
    if observed:
        try:
            observed_at = datetime.fromisoformat(observed.replace("Z", "+00:00"))
        except ValueError:
            pass
    return MarketObservation(
        asset_id=asset_id,
        symbol=str(item.get("symbol") or ""),
        name=str(item.get("name") or ""),
        price=_float(usd.get("price")),
        price_change_24h=_float(usd.get("percent_change_24h")),
        volume_24h=_float(usd.get("volume_24h")),
        volume_change_24h=_float(usd.get("volume_change_24h")),
        market_cap=_float(usd.get("market_cap")),
        market_cap_rank=_int(item.get("cmc_rank") or usd.get("market_cap_rank")),
        previous_market_cap_rank=previous,
        observed_at=observed_at,
    )


def normalize_listings(payload: dict, previous_ranks: dict[int, int] | None = None) -> list[MarketObservation]:
    data = payload.get("data") or []
    if isinstance(data, dict):
        data = list(data.values())
    return [normalize_listing(item, previous_ranks) for item in data if isinstance(item, dict)]


def normalize_global_metrics(payload: dict, context: MarketContext | None = None) -> MarketContext:
    data = payload.get("data") or {}
    quote = data.get("quote") or {}
    usd = quote.get("USD") or next(iter(quote.values()), {}) or {}
    ctx = context or MarketContext()
    return ctx.model_copy(
        update={
            "btc_dominance": _float(data.get("btc_dominance")),
            "eth_dominance": _float(data.get("eth_dominance")),
            "total_market_cap": _float(usd.get("total_market_cap")),
        }
    )


def normalize_fear_greed(payload: dict) -> MarketContext:
    data = payload.get("data") or payload
    if isinstance(data, list):
        data = data[0] if data else {}
    value = data.get("value") or data.get("score")
    label = data.get("value_classification") or data.get("classification") or data.get("name")
    return MarketContext(
        fear_greed_value=_int(value),
        fear_greed_label=str(label) if label else None,
    )


def is_stablecoin(observation: MarketObservation) -> bool:
    return observation.symbol.upper() in STABLECOIN_SYMBOLS


def _float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
