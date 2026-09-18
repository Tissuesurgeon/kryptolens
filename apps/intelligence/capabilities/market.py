from __future__ import annotations

from apps.intelligence.calculations import aggregate_mean, category_comparison, market_breadth
from apps.intelligence.capabilities.base import CapabilityResult, observation_rows
from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.observations import MarketContext, MarketObservation


class MarketCapability:
    name = "market"

    def accepts(self, task: ClarifiedTask) -> bool:
        return True

    def required_tools(self, task: ClarifiedTask) -> list[str]:
        tools = ["get_quotes"]
        if task.scope.universe.startswith("top") or task.task_type in {"scheduled_brief", "watch_plus_investigate"}:
            tools = ["get_market_listings", "get_global_metrics", "get_fear_and_greed"]
        elif len(task.scope.assets) > 1:
            tools = ["get_quotes"]
        return tools

    def analyze(
        self,
        observations: list[MarketObservation],
        context: MarketContext | None,
        task: ClarifiedTask,
        extras: dict | None = None,
    ) -> CapabilityResult:
        extras = extras or {}
        breadth = market_breadth(observations)
        mean = aggregate_mean(observations, "price_change_24h")
        claims: list[str] = []
        if breadth["assets"]:
            declining = breadth["percent_declining"]
            if declining is not None:
                claims.append(f"{declining:.0f}% of the observed universe declined over 24 hours.")
            if mean is not None:
                direction = "up" if mean > 0 else "down" if mean < 0 else "unchanged"
                claims.append(f"Mean 24h change is {direction} {abs(mean):.2f}%.")
        for item in observations[:3]:
            if item.price_change_24h is None:
                continue
            direction = "up" if item.price_change_24h > 0 else "down" if item.price_change_24h < 0 else "unchanged"
            claims.append(
                f"{item.symbol} is {direction} {abs(item.price_change_24h):.2f}% over 24 hours."
            )
        if context and context.fear_greed_value is not None:
            claims.append(
                f"Fear & Greed is {context.fear_greed_value}"
                + (f" ({context.fear_greed_label})." if context.fear_greed_label else ".")
            )
        categories = extras.get("categories") or {}
        comparison = category_comparison(categories) if categories else []
        limitations = []
        if extras.get("index_unavailable"):
            limitations.append("CMC index is not on this plan.")
        return CapabilityResult(
            name=self.name,
            claims=claims[:8],
            metrics={"breadth": breadth, "mean_price_change_24h": mean, "category_comparison": comparison},
            rows=observation_rows(observations)[:20],
            limitations=limitations,
        )
