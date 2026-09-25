from __future__ import annotations

from apps.intelligence.calculations import rank_change, relative_performance, volume_ratio
from apps.intelligence.capabilities.base import CapabilityResult
from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.observations import MarketContext, MarketObservation


class AnomalyCapability:
    name = "anomaly"

    def accepts(self, task: ClarifiedTask) -> bool:
        return self.name in task.capabilities or task.task_type in {"persistent_monitor", "watch_plus_investigate"}

    def required_tools(self, task: ClarifiedTask) -> list[str]:
        return ["get_quotes", "get_market_listings", "get_trending"]

    def analyze(
        self,
        observations: list[MarketObservation],
        context: MarketContext | None,
        task: ClarifiedTask,
        extras: dict | None = None,
    ) -> CapabilityResult:
        _ = context, extras
        price_bar, volume_bar = _criteria(task)
        baseline = next((item for item in observations if item.symbol.upper() == "BTC"), None)
        flagged: list[dict] = []
        claims: list[str] = []
        for item in observations:
            rel = relative_performance(item, baseline) if baseline and item is not baseline else None
            vol = volume_ratio(item)
            change = rank_change(item)
            unusual_price = item.price_change_24h is not None and abs(item.price_change_24h) >= price_bar
            unusual_volume = vol is not None and abs(vol) >= volume_bar
            if unusual_price or unusual_volume or (change is not None and abs(change) >= 5):
                flagged.append(
                    {
                        "symbol": item.symbol,
                        "price_change_24h": item.price_change_24h,
                        "volume_change_24h": item.volume_change_24h,
                        "relative_to_btc": rel,
                        "rank_change": change,
                    }
                )
        for row in flagged[:5]:
            bits = [row["symbol"]]
            if row.get("price_change_24h") is not None:
                bits.append(f"price {row['price_change_24h']:.2f}%")
            if row.get("volume_change_24h") is not None:
                bits.append(f"volume {row['volume_change_24h']:.1f}%")
            claims.append("Unusual activity: " + ", ".join(bits) + ".")
        if not claims:
            claims.append("No unusual price, volume, or rank moves met the configured bars.")
        return CapabilityResult(name=self.name, claims=claims, metrics={"flagged": len(flagged)}, rows=flagged)


def _criteria(task: ClarifiedTask) -> tuple[float, float]:
    price_bar = 5.0
    volume_bar = 80.0
    for cond in task.trigger.conditions or []:
        if not isinstance(cond, dict):
            continue
        metric = str(cond.get("metric") or "")
        try:
            value = abs(float(cond.get("value")))
        except (TypeError, ValueError):
            continue
        if metric == "price_change_24h":
            price_bar = value
        elif metric == "volume_change_24h":
            volume_bar = value
    return price_bar, volume_bar
