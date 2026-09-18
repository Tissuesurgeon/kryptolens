from __future__ import annotations

from apps.intelligence.calculations import historical_comparison
from apps.intelligence.capabilities.base import CapabilityResult
from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.observations import MarketContext, MarketObservation


class HistoricalCapability:
    name = "historical"

    def accepts(self, task: ClarifiedTask) -> bool:
        return self.name in task.capabilities or bool(task.scope.window)

    def required_tools(self, task: ClarifiedTask) -> list[str]:
        return ["get_quotes_historical", "get_ohlcv_historical"]

    def analyze(
        self,
        observations: list[MarketObservation],
        context: MarketContext | None,
        task: ClarifiedTask,
        extras: dict | None = None,
    ) -> CapabilityResult:
        _ = context
        extras = extras or {}
        series = extras.get("historical") or []
        claims: list[str] = []
        rows: list[dict] = []
        limitations = ["comparable observations, not a prediction."]
        if not series:
            limitations.append("comparable observations require historical quotes.")
            for item in observations:
                claims.append(f"{item.symbol} live quote is available; historical window was not returned.")
            return CapabilityResult(name=self.name, claims=claims, rows=rows, limitations=limitations)
        by_symbol: dict[str, list] = {}
        for item in series:
            symbol = (item.symbol if hasattr(item, "symbol") else item.get("symbol") or "").upper()
            by_symbol.setdefault(symbol, []).append(item)
        for symbol, points in by_symbol.items():
            first = points[0]
            last = points[-1]
            first_price = first.price if hasattr(first, "price") else first.get("price")
            last_price = last.price if hasattr(last, "price") else last.get("price")
            compared = historical_comparison(last_price, first_price)
            rows.append({"symbol": symbol, **compared})
            if compared["percent_change"] is not None:
                claims.append(
                    f"{symbol} changed {compared['percent_change']:.2f}% across the comparable window."
                )
        if not claims:
            claims.append("Historical quotes were fetched but no comparable percent could be calculated.")
        return CapabilityResult(name=self.name, claims=claims, metrics={"windows": len(rows)}, rows=rows, limitations=limitations)
