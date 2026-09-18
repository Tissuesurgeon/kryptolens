from __future__ import annotations

from collections.abc import Callable

from apps.intelligence.engine import compare
from apps.intelligence.observations import MarketObservation

CALCULATION_NAMES = (
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
)


def calculate_percentage_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return ((current - previous) / previous) * 100


def difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def ratio(left: float | None, right: float | None) -> float | None:
    if left is None or right in (None, 0):
        return None
    return left / right


def sort_assets(
    observations: list[MarketObservation],
    field: str = "price_change_24h",
    order: str = "ascending",
) -> list[MarketObservation]:
    reverse = order == "descending"

    def key(item: MarketObservation):
        value = item.metric_value(field)
        return (value is None, value if value is not None else 0)

    return sorted(observations, key=key, reverse=reverse)


def rank_assets(
    observations: list[MarketObservation],
    field: str = "price_change_24h",
    order: str = "ascending",
) -> list[dict]:
    ranked = sort_assets(observations, field=field, order=order)
    rows = []
    for index, item in enumerate(ranked, start=1):
        rows.append(
            {
                "rank": index,
                "symbol": item.symbol,
                "name": item.name,
                "asset_id": item.asset_id,
                "price": item.price,
                "price_change_24h": item.price_change_24h,
                "volume_24h": item.volume_24h,
                "market_cap": item.market_cap,
                "cmc_rank": item.market_cap_rank,
            }
        )
    return rows


def filter_threshold(
    observations: list[MarketObservation],
    field: str,
    operator: str,
    value,
) -> list[MarketObservation]:
    kept = []
    for item in observations:
        actual = item.metric_value(field)
        if actual is None:
            continue
        if compare(actual, operator, value):
            kept.append(item)
    return kept


def aggregate_mean(observations: list[MarketObservation], field: str) -> float | None:
    values = [item.metric_value(field) for item in observations]
    numbers = [item for item in values if isinstance(item, (int, float))]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def market_breadth(observations: list[MarketObservation], field: str = "price_change_24h") -> dict:
    changes = [item.metric_value(field) for item in observations]
    numbers = [item for item in changes if isinstance(item, (int, float))]
    total = len(numbers)
    advancing = sum(1 for item in numbers if item > 0)
    declining = sum(1 for item in numbers if item < 0)
    unchanged = total - advancing - declining
    share = (declining / total * 100) if total else None
    return {
        "assets": total,
        "advancing": advancing,
        "declining": declining,
        "unchanged": unchanged,
        "percent_declining": share,
        "percent_advancing": (advancing / total * 100) if total else None,
    }


def relative_performance(
    observation: MarketObservation,
    baseline: MarketObservation | float | None,
    field: str = "price_change_24h",
) -> float | None:
    actual = observation.metric_value(field)
    if isinstance(baseline, MarketObservation):
        baseline_value = baseline.metric_value(field)
    else:
        baseline_value = baseline
    return difference(actual if isinstance(actual, (int, float)) else None, baseline_value if isinstance(baseline_value, (int, float)) else None)


def volume_ratio(observation: MarketObservation, baseline: float | None = None) -> float | None:
    if baseline is None:
        return observation.volume_change_24h
    return ratio(observation.volume_24h, baseline)


def rank_change(observation: MarketObservation) -> int | None:
    if observation.market_cap_rank is None or observation.previous_market_cap_rank is None:
        return None
    return observation.previous_market_cap_rank - observation.market_cap_rank


def historical_comparison(current: float | None, previous: float | None) -> dict:
    change = calculate_percentage_change(current, previous)
    return {
        "current": current,
        "previous": previous,
        "percent_change": change,
        "limitation": "comparable observations, not a prediction.",
    }


def category_comparison(groups: dict[str, list[MarketObservation]], field: str = "price_change_24h") -> list[dict]:
    rows = []
    for name, items in groups.items():
        mean = aggregate_mean(items, field)
        breadth = market_breadth(items, field)
        rows.append({"category": name, "mean": mean, "assets": len(items), **breadth})
    return rows


REGISTRY: dict[str, Callable] = {
    "percentage_change": calculate_percentage_change,
    "difference": difference,
    "ratio": ratio,
    "ranking": rank_assets,
    "sorting": sort_assets,
    "threshold": filter_threshold,
    "aggregation": aggregate_mean,
    "market_breadth": market_breadth,
    "relative_performance": relative_performance,
    "volume_ratio": volume_ratio,
    "rank_change": rank_change,
    "historical_comparison": historical_comparison,
    "category_comparison": category_comparison,
}


def run_calculation(name: str, *args, **kwargs):
    if name not in REGISTRY:
        raise ValueError(f"unknown calculation: {name}")
    return REGISTRY[name](*args, **kwargs)
