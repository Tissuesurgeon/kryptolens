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
    return _usd_quote(item.get("quote") or item.get("quotes"))


def _usd_quote(quote) -> dict:
    """CMC v1 uses quote.USD; v3 listings/quotes return quote as a list of currency objects."""
    if isinstance(quote, list):
        for entry in quote:
            if isinstance(entry, dict) and str(entry.get("symbol") or entry.get("name") or "").upper() == "USD":
                return entry
        return next((entry for entry in quote if isinstance(entry, dict)), {}) or {}
    if isinstance(quote, dict):
        usd = quote.get("USD")
        if isinstance(usd, dict):
            return usd
        first = next(iter(quote.values()), {})
        return first if isinstance(first, dict) else {}
    return {}


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


def flatten_historical_quotes(payload: dict) -> dict:
    """Turn CMC quotes/historical into the quotes/latest shape normalize_listings expects."""
    data = payload.get("data") or {}
    items = []
    if isinstance(data, dict):
        values = data.values()
    elif isinstance(data, list):
        values = data
    else:
        values = []
    for asset in values:
        if not isinstance(asset, dict):
            continue
        quotes = asset.get("quotes") or asset.get("quote") or []
        last = {}
        if isinstance(quotes, list) and quotes:
            last = quotes[-1] if isinstance(quotes[-1], dict) else {}
        elif isinstance(quotes, dict):
            last = quotes
        quote = last.get("quote") if isinstance(last.get("quote"), (dict, list)) else last
        item = {
            "id": asset.get("id"),
            "name": asset.get("name"),
            "symbol": asset.get("symbol"),
            "cmc_rank": asset.get("cmc_rank") or asset.get("rank"),
            "last_updated": last.get("timestamp") or last.get("time_close") or asset.get("last_updated"),
            "quote": quote if quote else last,
        }
        items.append(item)
    return {"status": payload.get("status") or {}, "data": items}


def normalize_listings(payload: dict, previous_ranks: dict[int, int] | None = None) -> list[MarketObservation]:
    data = payload.get("data") or []
    items: list[dict] = []
    if isinstance(data, dict):
        values = data.values()
    elif isinstance(data, list):
        values = data
    else:
        values = []
    for item in values:
        if isinstance(item, list):
            items.extend(entry for entry in item if isinstance(entry, dict))
        elif isinstance(item, dict):
            items.append(item)
    return [normalize_listing(item, previous_ranks) for item in items]


def index_by_symbol(observations: list[MarketObservation]) -> dict[str, MarketObservation]:
    """One row per ticker. CMC v3 quotes return every asset that shares a symbol."""
    chosen: dict[str, MarketObservation] = {}
    for item in observations:
        key = (item.symbol or "").upper()
        if not key:
            continue
        current = chosen.get(key)
        if _better_listing(item, current):
            chosen[key] = item
    return chosen


def select_quoted_assets(
    payload: dict,
    symbols: list[str] | None = None,
    previous_ranks: dict[int, int] | None = None,
) -> list[MarketObservation]:
    observations = normalize_listings(payload, previous_ranks)
    by_symbol = index_by_symbol(observations)
    wanted = [(item or "").upper() for item in (symbols or []) if item]
    if wanted:
        picked = [by_symbol[key] for key in wanted if key in by_symbol]
        if picked:
            return picked
    return list(by_symbol.values()) or observations


def _better_listing(candidate: MarketObservation, current: MarketObservation | None) -> bool:
    if current is None:
        return True
    if (candidate.price is not None) != (current.price is not None):
        return candidate.price is not None
    cand_rank = candidate.market_cap_rank if candidate.market_cap_rank is not None else 10**9
    cur_rank = current.market_cap_rank if current.market_cap_rank is not None else 10**9
    if cand_rank != cur_rank:
        return cand_rank < cur_rank
    return (candidate.market_cap or 0) > (current.market_cap or 0)


def normalize_global_metrics(payload: dict, context: MarketContext | None = None) -> MarketContext:
    data = payload.get("data") or {}
    usd = _usd_quote(data.get("quote"))
    ctx = context or MarketContext()
    return ctx.model_copy(
        update={
            "btc_dominance": _float(data.get("btc_dominance")),
            "eth_dominance": _float(data.get("eth_dominance")),
            "total_market_cap": _float(usd.get("total_market_cap")),
        }
    )


def normalize_fear_greed(payload: dict, context: MarketContext | None = None) -> MarketContext:
    data = payload.get("data") or payload
    if isinstance(data, list):
        data = data[0] if data else {}
    value = data.get("value") or data.get("score")
    label = data.get("value_classification") or data.get("classification") or data.get("name")
    fields = {
        "fear_greed_value": _int(value),
        "fear_greed_label": str(label) if label else None,
    }
    if context is None:
        return MarketContext(**fields)
    return context.model_copy(update=fields)


def is_stablecoin(observation: MarketObservation) -> bool:
    return observation.symbol.upper() in STABLECOIN_SYMBOLS


def normalize_trending(payload: dict) -> list[MarketObservation]:
    return normalize_listings(_unwrap_data(payload))


def normalize_ohlcv(payload: dict) -> list[MarketObservation]:
    data = payload.get("data") or {}
    items: list[dict] = []
    values = data.values() if isinstance(data, dict) else data if isinstance(data, list) else []
    for asset in values:
        if not isinstance(asset, dict):
            continue
        quotes = asset.get("quotes") or asset.get("ohlcv") or []
        last = quotes[-1] if isinstance(quotes, list) and quotes else quotes if isinstance(quotes, dict) else {}
        quote = last.get("quote") if isinstance(last, dict) else {}
        usd = quote.get("USD") if isinstance(quote, dict) else last
        if not isinstance(usd, dict):
            usd = last if isinstance(last, dict) else {}
        items.append(
            {
                "id": asset.get("id"),
                "name": asset.get("name"),
                "symbol": asset.get("symbol"),
                "last_updated": (last or {}).get("time_close") or asset.get("last_updated"),
                "quote": {"USD": {"price": usd.get("close") or usd.get("price"), "volume_24h": usd.get("volume")}},
            }
        )
    return normalize_listings({"data": items})


def normalize_categories(payload: dict) -> list[dict]:
    data = payload.get("data")
    rows = data if isinstance(data, list) else list((data or {}).values()) if isinstance(data, dict) else []
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "id": row.get("id"),
                "name": row.get("name") or row.get("title"),
                "market_cap": row.get("market_cap"),
                "volume": row.get("volume") or row.get("volume_24h"),
            }
        )
    return items


def _unwrap_data(payload: dict) -> dict:
    data = payload.get("data")
    if isinstance(data, dict) and "cryptoCurrencies" in data:
        return {"data": data.get("cryptoCurrencies") or data.get("items") or []}
    if isinstance(data, dict) and any(key in data for key in ("gainers", "losers", "trending")):
        rows = []
        for key in ("gainers", "losers", "trending", "cryptoCurrencies"):
            rows.extend(item for item in (data.get(key) or []) if isinstance(item, dict))
        return {"data": rows}
    return payload


def normalize_content(payload: dict) -> list[dict]:
    """Normalize CMC /v1/content/latest into headline dicts with tagged assets."""
    data = payload.get("data")
    if isinstance(data, dict):
        rows = data.get("list") or data.get("items") or list(data.values())
    elif isinstance(data, list):
        rows = data
    else:
        rows = []
    items = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            continue
        assets = []
        for asset in row.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            symbol = str(asset.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            assets.append(
                {
                    "id": asset.get("id"),
                    "name": str(asset.get("name") or symbol),
                    "symbol": symbol,
                    "slug": str(asset.get("slug") or ""),
                }
            )
        items.append(
            {
                "title": title,
                "subtitle": str(row.get("subtitle") or "").strip(),
                "source_name": str(row.get("source_name") or "").strip(),
                "source_url": str(row.get("source_url") or "").strip(),
                "type": str(row.get("type") or "news").strip() or "news",
                "released_at": str(row.get("released_at") or row.get("created_at") or ""),
                "assets": assets,
            }
        )
    return items


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
