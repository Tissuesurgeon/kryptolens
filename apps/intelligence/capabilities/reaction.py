from __future__ import annotations

from apps.intelligence.calculations import market_breadth, relative_performance
from apps.intelligence.capabilities.base import CapabilityResult, observation_rows
from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.observations import MarketContext, MarketObservation


class ReactionCapability:
    name = "reaction"

    def accepts(self, task: ClarifiedTask) -> bool:
        return self.name in task.capabilities or task.task_type == "watch_plus_investigate"

    def required_tools(self, task: ClarifiedTask) -> list[str]:
        return ["get_quotes", "get_market_listings", "get_global_metrics"]

    def analyze(
        self,
        observations: list[MarketObservation],
        context: MarketContext | None,
        task: ClarifiedTask,
        extras: dict | None = None,
    ) -> CapabilityResult:
        _ = extras
        trigger_symbol = (task.trigger_asset() or (task.scope.assets[0] if task.scope.assets else "BTC")).upper()
        breadth = market_breadth(observations)
        trigger = next((item for item in observations if item.symbol.upper() == trigger_symbol), None)
        claims: list[str] = []
        if trigger and trigger.price_change_24h is not None:
            claims.append(f"{trigger_symbol} moved {trigger.price_change_24h:.2f}% over 24 hours.")
        if breadth.get("percent_declining") is not None:
            claims.append(f"{breadth['percent_declining']:.0f}% of the universe declined.")
        if trigger:
            steeper = []
            for item in observations:
                rel = relative_performance(item, trigger)
                if rel is not None and rel < 0 and item.symbol.upper() != trigger_symbol:
                    steeper.append(item)
            if steeper:
                names = ", ".join(item.symbol for item in steeper[:5])
                claims.append(f"Moved more than {trigger_symbol}: {names}.")
        if context and context.btc_dominance is not None:
            claims.append(f"BTC dominance is {context.btc_dominance:.2f}%.")
        return CapabilityResult(
            name=self.name,
            claims=claims,
            metrics={
                "breadth": breadth,
                "trigger_change": trigger.price_change_24h if trigger else None,
                "trigger_asset": trigger_symbol,
            },
            rows=observation_rows(observations)[:20],
        )
