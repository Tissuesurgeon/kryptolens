from __future__ import annotations

from .observations import QueryPlan
from .policy import IntelligencePolicy

LISTINGS = "/v3/cryptocurrency/listings/latest"
QUOTES = "/v3/cryptocurrency/quotes/latest"
FEAR_GREED = "/v3/fear-and-greed/latest"
GLOBAL = "/v1/global-metrics/quotes/latest"

FIELD_MAP = {
    "price_change_24h": "percent_change_24h",
    "volume_change_24h": "volume_change_24h",
    "volume_24h": "volume_24h",
    "market_cap": "market_cap",
    "market_cap_rank": "cmc_rank",
    "price": "price",
}


def plan_query(policy: IntelligencePolicy) -> QueryPlan:
    endpoints: list[str] = []
    required = []
    for metric in policy.metrics.observed:
        field = FIELD_MAP.get(metric)
        if field and field not in required:
            required.append(field)
    for condition in policy.asset_conditions:
        field = FIELD_MAP.get(condition.metric)
        if field and field not in required:
            required.append(field)
    if "price" not in required:
        required.insert(0, "price")

    needs_rank = "rank_improved" in policy.metrics.derived or any(
        item.metric == "rank_improved" for item in policy.asset_conditions
    )
    if needs_rank and "cmc_rank" not in required:
        required.append("cmc_rank")

    parameters: dict = {"convert": "USD"}
    quote_symbols: list[str] = []

    if policy.universe.type == "symbols":
        endpoints.append(QUOTES)
        quote_symbols = list(policy.universe.symbols)
        parameters["symbol"] = ",".join(quote_symbols)
    else:
        endpoints.append(LISTINGS)
        parameters["start"] = 1
        parameters["limit"] = policy.universe.limit

    include_context = []
    if "fear_greed" in policy.metrics.context or any(
        item.metric == "fear_greed" for item in policy.market_context
    ):
        endpoints.append(FEAR_GREED)
        include_context.append("fear_greed")

    global_metrics = {"btc_dominance", "eth_dominance", "total_market_cap"}
    if any(item in global_metrics for item in policy.metrics.context) or any(
        item.metric in global_metrics for item in policy.market_context
    ):
        endpoints.append(GLOBAL)
        include_context.append("global_metrics")

    return QueryPlan(
        endpoints=endpoints,
        parameters=parameters,
        required_fields=required,
        requires_previous_snapshot=needs_rank,
        include_context=include_context,
        quote_symbols=quote_symbols,
    )
