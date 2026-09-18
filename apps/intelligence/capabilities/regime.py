from __future__ import annotations

from apps.intelligence.calculations import aggregate_mean, market_breadth
from apps.intelligence.capabilities.base import CapabilityResult
from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.observations import MarketContext, MarketObservation


class RegimeCapability:
    name = "regime"

    def accepts(self, task: ClarifiedTask) -> bool:
        return self.name in task.capabilities or task.task_type == "scheduled_brief"

    def required_tools(self, task: ClarifiedTask) -> list[str]:
        return ["get_quotes", "get_market_listings", "get_global_metrics", "get_fear_and_greed", "get_altcoin_season"]

    def analyze(
        self,
        observations: list[MarketObservation],
        context: MarketContext | None,
        task: ClarifiedTask,
        extras: dict | None = None,
    ) -> CapabilityResult:
        _ = task
        extras = extras or {}
        breadth = market_breadth(observations)
        btc = next((item for item in observations if item.symbol.upper() == "BTC"), None)
        mean = aggregate_mean(observations, "price_change_24h")
        claims: list[str] = []
        btc_led = False
        if btc and btc.price_change_24h is not None and mean is not None:
            btc_led = abs(btc.price_change_24h) >= abs(mean) and (
                (btc.price_change_24h < 0 and (breadth.get("percent_declining") or 0) < 60)
                or (btc.price_change_24h > 0 and (breadth.get("percent_advancing") or 0) < 60)
            )
            if btc_led:
                claims.append("BTC-led tape: Bitcoin's move is larger than the universe mean.")
            else:
                claims.append("Broad tape: the universe move is not just Bitcoin.")
        if context and context.fear_greed_label:
            claims.append(f"Fear & Greed classification is {context.fear_greed_label}.")
        limitations = []
        if extras.get("altcoin_season_unavailable"):
            limitations.append(extras["altcoin_season_unavailable"])
        elif extras.get("altcoin_season") is not None:
            claims.append(f"Altcoin season reading: {extras['altcoin_season']}.")
        if extras.get("index_unavailable"):
            limitations.append("CMC index is not on this plan.")
        return CapabilityResult(
            name=self.name,
            claims=claims or ["Regime rules need BTC, breadth, and Fear & Greed from live CMC."],
            metrics={"btc_led": btc_led, "breadth": breadth, "mean": mean},
            limitations=limitations,
        )
