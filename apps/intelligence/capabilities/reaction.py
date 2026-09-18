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
        breadth = market_breadth(observations)
        btc = next((item for item in observations if item.symbol.upper() == "BTC"), None)
        claims: list[str] = []
        if btc and btc.price_change_24h is not None:
            claims.append(f"BTC moved {btc.price_change_24h:.2f}% over 24 hours.")
        if breadth.get("percent_declining") is not None:
            claims.append(f"{breadth['percent_declining']:.0f}% of the universe declined.")
        if btc:
            steeper = []
            for item in observations:
                rel = relative_performance(item, btc)
                if rel is not None and rel < 0 and item.symbol.upper() != "BTC":
                    steeper.append(item)
            if steeper:
                names = ", ".join(item.symbol for item in steeper[:5])
                claims.append(f"Moved more than BTC: {names}.")
        if context and context.btc_dominance is not None:
            claims.append(f"BTC dominance is {context.btc_dominance:.2f}%.")
        return CapabilityResult(
            name=self.name,
            claims=claims,
            metrics={"breadth": breadth, "btc_change": btc.price_change_24h if btc else None},
            rows=observation_rows(observations)[:20],
        )
