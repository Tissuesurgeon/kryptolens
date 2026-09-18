from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field

from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.observations import MarketContext, MarketObservation


class CapabilityResult(BaseModel):
    name: str
    claims: list[str] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    rows: list[dict] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class Capability(Protocol):
    name: str

    def accepts(self, task: ClarifiedTask) -> bool: ...

    def required_tools(self, task: ClarifiedTask) -> list[str]: ...

    def analyze(
        self,
        observations: list[MarketObservation],
        context: MarketContext | None,
        task: ClarifiedTask,
        extras: dict | None = None,
    ) -> CapabilityResult: ...


def observation_rows(observations: list[MarketObservation]) -> list[dict]:
    rows = []
    for item in observations:
        rows.append(
            {
                "asset_id": item.asset_id,
                "symbol": item.symbol,
                "name": item.name,
                "price": item.price,
                "price_change_24h": item.price_change_24h,
                "volume_24h": item.volume_24h,
                "market_cap": item.market_cap,
                "cmc_rank": item.market_cap_rank,
            }
        )
    return rows
