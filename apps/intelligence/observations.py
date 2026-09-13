from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class MarketObservation(BaseModel):
    asset_id: int
    symbol: str
    name: str = ""
    price: float | None = None
    price_change_24h: float | None = None
    volume_24h: float | None = None
    volume_change_24h: float | None = None
    market_cap: float | None = None
    market_cap_rank: int | None = None
    previous_market_cap_rank: int | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def rank_improved(self) -> bool | None:
        if self.market_cap_rank is None or self.previous_market_cap_rank is None:
            return None
        return self.market_cap_rank < self.previous_market_cap_rank

    def metric_value(self, metric: str):
        if metric == "rank_improved":
            return self.rank_improved
        return getattr(self, metric, None)


class MarketContext(BaseModel):
    fear_greed_value: int | None = None
    fear_greed_label: str | None = None
    btc_dominance: float | None = None
    eth_dominance: float | None = None
    total_market_cap: float | None = None
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def metric_value(self, metric: str):
        if metric == "fear_greed":
            return self.fear_greed_value
        if metric in {"btc_dominance", "eth_dominance", "total_market_cap"}:
            return getattr(self, metric, None)
        return None


class QueryPlan(BaseModel):
    endpoints: list[str]
    parameters: dict = Field(default_factory=dict)
    required_fields: list[str] = Field(default_factory=list)
    requires_previous_snapshot: bool = False
    include_context: list[str] = Field(default_factory=list)
    quote_symbols: list[str] = Field(default_factory=list)


class Candidate(BaseModel):
    observation: MarketObservation
    context: MarketContext | None = None
    conditions_evaluated: int = 0
    conditions_met: int = 0
    condition_results: list[dict] = Field(default_factory=list)
    logic_passed: bool = False
    score: int = 0
    reasons: list[str] = Field(default_factory=list)
    severity: str = "low"
    context_confirmed: bool = False
    skipped_metrics: list[str] = Field(default_factory=list)
    should_promote: bool = False
    should_notify: bool = False
    suppress_reason: str = ""
