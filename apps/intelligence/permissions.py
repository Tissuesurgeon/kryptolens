from __future__ import annotations

from apps.intelligence.tools import ToolPermissionError

READ = "READ"
ANALYZE = "ANALYZE"
SIMULATE = "SIMULATE"
PREPARE = "PREPARE"
REQUEST_APPROVAL = "REQUEST_APPROVAL"
EXECUTE = "EXECUTE"

ALLOWED_NOW = frozenset({READ, ANALYZE})
DENIED_NOW = frozenset({SIMULATE, PREPARE, REQUEST_APPROVAL, EXECUTE})

TOOL_SENSITIVITY = {
    "get_market_listings": READ,
    "get_quotes": READ,
    "get_quotes_historical": READ,
    "get_ohlcv_historical": READ,
    "get_global_metrics": READ,
    "get_fear_and_greed": READ,
    "get_content": READ,
    "get_trending": READ,
    "get_gainers_losers": READ,
    "get_new_listings": READ,
    "get_categories": READ,
    "get_category": READ,
    "get_price_performance": READ,
    "get_altcoin_season": READ,
    "get_cmc_index": READ,
    "calculate": ANALYZE,
    "sort": ANALYZE,
    "present": ANALYZE,
    "news": READ,
    "on_chain": READ,
    "derivatives": READ,
    "dex": READ,
    "rwa": READ,
}


def sensitivity_for(name: str) -> str:
    return TOOL_SENSITIVITY.get(name, name)


def is_allowed_now(name: str) -> bool:
    return sensitivity_for(name) in ALLOWED_NOW


def require_sensitivity(name: str) -> str:
    sensitivity = sensitivity_for(name)
    if sensitivity in DENIED_NOW or name in DENIED_NOW:
        raise ToolPermissionError(f"{name} is not available yet.")
    if sensitivity not in ALLOWED_NOW:
        raise ToolPermissionError(f"{name} is not available yet.")
    return sensitivity
