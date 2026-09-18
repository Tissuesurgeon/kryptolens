from __future__ import annotations

from apps.cmc.adapter import CMCAdapter, CMCError
from apps.cmc.logging import persist_call
from apps.cmc.normalize import (
    is_stablecoin,
    normalize_content,
    normalize_fear_greed,
    normalize_global_metrics,
    normalize_listings,
    normalize_ohlcv,
    normalize_trending,
    select_quoted_assets,
)
from apps.intelligence.news import analyze_news, attach_quotes, build_news_payload, symbols_from_items
from apps.intelligence.present import comparison_title
from apps.intelligence.calculations import aggregate_mean, filter_threshold, rank_assets, sort_assets
from apps.intelligence.engine import compare
from apps.intelligence.observations import MarketObservation
from apps.intelligence.tools import ToolPermissionError, dispatch_cmc
from apps.intelligence.workflow import WorkflowDefinition, WorkflowTrigger


class WorkflowExecutionError(Exception):
    pass


def trigger_fired(trigger: WorkflowTrigger | None, observations: list[MarketObservation]) -> tuple[bool, MarketObservation | None]:
    if not trigger or trigger.type != "asset_condition":
        return True, None
    asset = (trigger.asset or "").upper()
    match = next((item for item in observations if item.symbol.upper() == asset), None)
    if match is None:
        return False, None
    actual = match.metric_value(trigger.metric)
    if actual is None or trigger.value is None:
        return False, match
    return compare(actual, trigger.operator, trigger.value), match


def execute_steps(
    adapter: CMCAdapter,
    workflow: WorkflowDefinition,
    permissions: dict,
    run,
    *,
    exclude_stablecoins: bool = True,
    previous_ranks: dict | None = None,
) -> dict:
    observations: list[MarketObservation] = []
    tools_used: list[str] = []
    context = None
    btc_observation = None
    present_format = "ranked_table"
    present_operation = ""
    present_limit = None
    rank_order = "ascending"
    limit = 100
    listings_fetched = False
    news_items: list[dict] = []
    extras: dict = {}

    for step in workflow.steps:
        if step.type in {"get_universe", "get_market_data"}:
            limit = step.limit or limit
            if listings_fetched:
                continue
            run.set_stage("fetching_cmc")
            call = dispatch_cmc(adapter, "get_market_listings", permissions, limit=limit)
            persist_call(call, run)
            tools_used.append("get_market_listings")
            observations = normalize_listings(call.payload, previous_ranks)
            if exclude_stablecoins:
                observations = [item for item in observations if not is_stablecoin(item)]
            listings_fetched = True
        elif step.type == "get_quotes":
            run.set_stage("fetching_cmc")
            symbols = list(step.symbols or []) or symbols_from_items(news_items) or ["BTC"]
            call = dispatch_cmc(adapter, "get_quotes", permissions, symbols=symbols)
            persist_call(call, run)
            tools_used.append("get_quotes")
            observations = select_quoted_assets(call.payload, symbols, previous_ranks)
        elif step.type == "get_global_metrics":
            call = dispatch_cmc(adapter, "get_global_metrics", permissions)
            persist_call(call, run)
            tools_used.append("get_global_metrics")
            context = normalize_global_metrics(call.payload, context)
        elif step.type == "get_fear_and_greed":
            call = dispatch_cmc(adapter, "get_fear_and_greed", permissions)
            persist_call(call, run)
            tools_used.append("get_fear_and_greed")
            context = normalize_fear_greed(call.payload, context)
        elif step.type == "get_content":
            run.set_stage("fetching_cmc")
            news_type = step.source if step.source in {"news", "community", "alexandria", "all"} else "news"
            call = dispatch_cmc(
                adapter,
                "get_content",
                permissions,
                start=1,
                limit=step.limit or 20,
                symbols=list(step.symbols or []),
                news_type=news_type,
            )
            persist_call(call, run)
            tools_used.append("get_content")
            news_items = normalize_content(call.payload)
        elif step.type == "get_quotes_historical":
            extras.update(
                _optional_tool(
                    adapter,
                    permissions,
                    run,
                    tools_used,
                    "get_quotes_historical",
                    "historical_unavailable",
                    symbols=list(step.symbols or []),
                    window=step.operation or "30d",
                )
            )
            if extras.get("historical_call"):
                extras["historical"] = select_quoted_assets(extras["historical_call"].payload, list(step.symbols or []))
        elif step.type == "get_ohlcv_historical":
            extras.update(
                _optional_tool(
                    adapter,
                    permissions,
                    run,
                    tools_used,
                    "get_ohlcv_historical",
                    "ohlcv_unavailable",
                    symbols=list(step.symbols or []),
                    window=step.operation or "30d",
                )
            )
            if extras.get("ohlcv_call"):
                extras["ohlcv"] = normalize_ohlcv(extras["ohlcv_call"].payload)
        elif step.type == "get_trending":
            extras.update(
                _optional_tool(adapter, permissions, run, tools_used, "get_trending", "trending_unavailable")
            )
            if extras.get("trending_call"):
                extras["trending"] = normalize_trending(extras["trending_call"].payload)
        elif step.type == "get_gainers_losers":
            extras.update(
                _optional_tool(adapter, permissions, run, tools_used, "get_gainers_losers", "gainers_unavailable")
            )
            if extras.get("gainers_call"):
                extras["gainers"] = normalize_trending(extras["gainers_call"].payload)
        elif step.type == "get_new_listings":
            extras.update(
                _optional_tool(
                    adapter, permissions, run, tools_used, "get_new_listings", "new_listings_unavailable", limit=step.limit or 20
                )
            )
            if extras.get("new_listings_call"):
                extras["new_listings"] = normalize_listings(extras["new_listings_call"].payload)
        elif step.type == "get_categories":
            extras.update(
                _optional_tool(adapter, permissions, run, tools_used, "get_categories", "categories_unavailable")
            )
        elif step.type == "calculate":
            run.set_stage("analyzing")
            # percent_change_24h is already on each observation from CMC
            if step.operation and step.operation not in {
                "percentage_change",
                "difference",
                "ratio",
                "ranking",
                "sorting",
                "threshold",
                "aggregation",
                "market_breadth",
                "relative_performance",
                "volume_ratio",
                "rank_change",
                "historical_comparison",
                "category_comparison",
            }:
                raise WorkflowExecutionError(f"unknown calculation: {step.operation}")
        elif step.type == "sort":
            run.set_stage("analyzing")
            rank_order = step.order or "ascending"
            observations = sort_assets(observations, field=step.field or "price_change_24h", order=rank_order)
        elif step.type == "filter":
            run.set_stage("analyzing")
            if step.relative_to:
                reference = _reference_change(adapter, permissions, run, tools_used, step.relative_to, observations)
                if reference is not None:
                    observations = [
                        item
                        for item in observations
                        if item.price_change_24h is not None and item.price_change_24h < reference
                    ]
                    btc_observation = btc_observation or next(
                        (item for item in observations if item.symbol.upper() == step.relative_to.upper()),
                        None,
                    )
            elif step.field and step.operator is not None and step.value is not None:
                observations = filter_threshold(observations, step.field, step.operator, step.value)
        elif step.type == "aggregate":
            run.set_stage("analyzing")
        elif step.type == "present":
            present_format = step.format or "ranked_table"
            present_operation = step.operation or ""
            present_limit = step.limit
        else:
            raise WorkflowExecutionError(f"unknown workflow step: {step.type}")

    payload: dict
    if present_format == "news_brief":
        run.set_stage("analyzing")
        attached = attach_quotes(news_items, observations)
        if not attached:
            payload = {
                "message": "CoinMarketCap returned no News/Headlines for this request.",
                "items": [],
                "rows": [],
                "assets": len(observations),
                "headlines": 0,
            }
            kind = "no_result"
            title = "No headlines"
        else:
            analysis = analyze_news(attached, observations)
            payload = build_news_payload(attached, observations, analysis)
            kind = "news_brief"
            title = "Market news"
    elif present_format == "comparison":
        payload = {
            "rows": [
                {
                    "symbol": item.symbol,
                    "name": item.name,
                    "price": item.price,
                    "price_change_24h": item.price_change_24h,
                    "market_cap": item.market_cap,
                }
                for item in observations
            ]
        }
        kind = "comparison"
        title = comparison_title(observations)
    elif present_format == "market_summary":
        mean_move = aggregate_mean(observations, "price_change_24h")
        payload = {
            "assets": len(observations),
            "mean_price_change_24h": mean_move,
            "context": context.model_dump(mode="json") if context else {},
            "leaders": rank_assets(observations, "price_change_24h", "ascending")[:5],
        }
        kind = "market_summary"
        title = "Market summary"
    else:
        rows = rank_assets(observations, "price_change_24h", rank_order)
        if present_limit:
            rows = rows[:present_limit]
        payload = {
            "rows": rows,
            "assets": len(observations),
            "direction": present_operation or ("gainers" if rank_order == "descending" else ""),
        }
        kind = "ranked_table"
        if present_operation == "gainers":
            title = "Highest 24h gains"
        elif present_operation == "losers":
            title = "Biggest 24h declines"
        else:
            title = "Market reaction"

    return {
        "kind": kind,
        "title": title,
        "payload": payload,
        "observations": observations,
        "tools_used": tools_used,
        "btc": btc_observation,
        "context": context,
        "extras": extras,
    }


def _optional_tool(adapter, permissions, run, tools_used, name: str, unavailable_key: str, **kwargs) -> dict:
    extras: dict = {}
    try:
        run.set_stage("fetching_cmc")
        call = dispatch_cmc(adapter, name, permissions, **kwargs)
        persist_call(call, run)
        tools_used.append(name)
        extras[f"{name.replace('get_', '')}_call"] = call
        if name == "get_quotes_historical":
            extras["historical_call"] = call
        elif name == "get_ohlcv_historical":
            extras["ohlcv_call"] = call
        elif name == "get_trending":
            extras["trending_call"] = call
        elif name == "get_gainers_losers":
            extras["gainers_call"] = call
        elif name == "get_new_listings":
            extras["new_listings_call"] = call
    except (CMCError, ToolPermissionError) as exc:
        extras[unavailable_key] = str(exc)
    return extras


def fetch_trigger_asset(adapter: CMCAdapter, permissions: dict, run, symbol: str) -> MarketObservation | None:
    call = dispatch_cmc(adapter, "get_quotes", permissions, symbols=[symbol])
    persist_call(call, run)
    observations = select_quoted_assets(call.payload, [symbol])
    return observations[0] if observations else None


def _reference_change(adapter, permissions, run, tools_used, symbol: str, observations: list[MarketObservation]) -> float | None:
    match = next((item for item in observations if item.symbol.upper() == symbol.upper()), None)
    if match and match.price_change_24h is not None:
        return match.price_change_24h
    try:
        quote = fetch_trigger_asset(adapter, permissions, run, symbol)
    except (CMCError, ToolPermissionError):
        return None
    tools_used.append("get_quotes")
    return quote.price_change_24h if quote else None
