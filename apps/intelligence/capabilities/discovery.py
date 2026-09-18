from __future__ import annotations

from apps.intelligence.calculations import rank_change
from apps.intelligence.capabilities.base import CapabilityResult
from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.observations import MarketContext, MarketObservation


class DiscoveryCapability:
    name = "discovery"

    def accepts(self, task: ClarifiedTask) -> bool:
        return self.name in task.capabilities

    def required_tools(self, task: ClarifiedTask) -> list[str]:
        return ["get_trending", "get_gainers_losers", "get_new_listings", "get_market_listings"]

    def analyze(
        self,
        observations: list[MarketObservation],
        context: MarketContext | None,
        task: ClarifiedTask,
        extras: dict | None = None,
    ) -> CapabilityResult:
        _ = context, task
        extras = extras or {}
        attention = extras.get("trending") or extras.get("gainers") or observations
        claims: list[str] = []
        rows: list[dict] = []
        for item in attention[:15]:
            volume_move = item.volume_change_24h is not None and abs(item.volume_change_24h) >= 40
            rank_move = rank_change(item)
            price_move = item.price_change_24h is not None and abs(item.price_change_24h) >= 5
            together = sum(bool(flag) for flag in (volume_move, rank_move, price_move)) >= 2
            row = {
                "symbol": item.symbol,
                "price_change_24h": item.price_change_24h,
                "volume_change_24h": item.volume_change_24h,
                "rank_change": rank_move,
                "attention_volume_rank": together,
            }
            rows.append(row)
            if together:
                claims.append(
                    f"{item.symbol} showed attention, volume, and rank moving together."
                )
        if extras.get("new_listings"):
            names = ", ".join(item.symbol for item in extras["new_listings"][:5] if getattr(item, "symbol", None))
            if names:
                claims.append(f"New listings observed: {names}.")
        if not claims:
            claims.append("No asset combined unusual attention, volume, and rank in this snapshot.")
        limitations = []
        for key in ("trending_unavailable", "gainers_unavailable", "new_listings_unavailable"):
            if extras.get(key):
                limitations.append(extras[key])
        return CapabilityResult(name=self.name, claims=claims, rows=rows, limitations=limitations)
