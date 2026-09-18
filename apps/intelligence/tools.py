from __future__ import annotations

from typing import Callable

from apps.cmc.adapter import CMCAdapter, CMCCall

DEFAULT_TOOL_PERMISSIONS = {
    "get_market_listings": True,
    "get_quotes": True,
    "get_quotes_historical": True,
    "get_ohlcv_historical": True,
    "get_global_metrics": True,
    "get_fear_and_greed": True,
    "get_content": True,
    "get_trending": True,
    "get_gainers_losers": True,
    "get_new_listings": True,
    "get_categories": True,
    "get_category": True,
    "get_price_performance": True,
    "get_altcoin_season": True,
    "get_cmc_index": True,
    "news": False,
    "on_chain": False,
    "derivatives": False,
    "dex": False,
    "rwa": False,
}

CMC_TOOL_NAMES = (
    "get_market_listings",
    "get_quotes",
    "get_quotes_historical",
    "get_ohlcv_historical",
    "get_global_metrics",
    "get_fear_and_greed",
    "get_content",
    "get_trending",
    "get_gainers_losers",
    "get_new_listings",
    "get_categories",
    "get_category",
    "get_price_performance",
    "get_altcoin_season",
    "get_cmc_index",
)

TOOL_GROUPS = {
    "market": ("get_market_listings", "get_quotes", "get_price_performance"),
    "historical": ("get_quotes_historical", "get_ohlcv_historical"),
    "discovery": ("get_trending", "get_gainers_losers", "get_new_listings"),
    "context": ("get_global_metrics", "get_fear_and_greed", "get_altcoin_season", "get_cmc_index"),
    "categories": ("get_categories", "get_category"),
    "content": ("get_content",),
}


class ToolPermissionError(PermissionError):
    pass


def tool_allowed(permissions: dict | None, name: str) -> bool:
    perms = dict(DEFAULT_TOOL_PERMISSIONS)
    if permissions:
        perms.update(permissions)
    return bool(perms.get(name))


def require_tool(permissions: dict | None, name: str) -> None:
    if name in {"on_chain", "news", "derivatives", "dex", "rwa"} or not tool_allowed(permissions, name):
        raise ToolPermissionError(f"Lens is not permitted to use {name}")


def dispatch_cmc(adapter: CMCAdapter, name: str, permissions: dict | None, **kwargs) -> CMCCall:
    require_tool(permissions, name)
    handlers: dict[str, Callable[..., CMCCall]] = {
        "get_market_listings": lambda: adapter.get_listings(
            start=int(kwargs.get("start", 1)),
            limit=int(kwargs.get("limit", 100)),
        ),
        "get_quotes": lambda: adapter.get_quotes(list(kwargs.get("symbols") or [])),
        "get_quotes_historical": lambda: adapter.get_quotes_historical_range(
            list(kwargs.get("symbols") or []),
            window=str(kwargs.get("window") or kwargs.get("operation") or "30d"),
            convert=str(kwargs.get("convert") or "USD"),
        ),
        "get_ohlcv_historical": lambda: adapter.get_ohlcv_historical(
            list(kwargs.get("symbols") or []),
            window=str(kwargs.get("window") or kwargs.get("operation") or "30d"),
            convert=str(kwargs.get("convert") or "USD"),
        ),
        "get_global_metrics": lambda: adapter.get_global_metrics(),
        "get_fear_and_greed": lambda: adapter.get_fear_greed(),
        "get_content": lambda: adapter.get_content_latest(
            start=int(kwargs.get("start", 1)),
            limit=int(kwargs.get("limit", 20)),
            symbols=list(kwargs.get("symbols") or []),
            news_type=str(kwargs.get("news_type") or "news"),
        ),
        "get_trending": lambda: adapter.get_trending_latest(),
        "get_gainers_losers": lambda: adapter.get_gainers_losers(),
        "get_new_listings": lambda: adapter.get_listings_new(limit=int(kwargs.get("limit", 20))),
        "get_categories": lambda: adapter.get_categories(limit=int(kwargs.get("limit", 50))),
        "get_category": lambda: adapter.get_category(str(kwargs.get("id") or kwargs.get("category_id") or "")),
        "get_price_performance": lambda: adapter.get_price_performance_stats(list(kwargs.get("symbols") or [])),
        "get_altcoin_season": lambda: adapter.get_altcoin_season(),
        "get_cmc_index": lambda: adapter.get_cmc_index(str(kwargs.get("symbol") or "CMC20")),
    }
    handler = handlers.get(name)
    if handler is None:
        raise ToolPermissionError(f"Unknown CMC tool: {name}")
    return handler()
