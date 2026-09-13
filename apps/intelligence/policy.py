from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Operator = Literal[">", ">=", "<", "<=", "=="]
Logic = Literal["AND", "OR"]
Severity = Literal["low", "medium", "high"]
UniverseType = Literal["listings", "symbols"]


class Condition(BaseModel):
    metric: str
    operator: Operator
    value: float | bool | int

    @field_validator("metric")
    @classmethod
    def metric_not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("metric is required")
        return cleaned


class Universe(BaseModel):
    type: UniverseType
    limit: int = Field(default=100, ge=1, le=500)
    exclude_stablecoins: bool = True
    symbols: list[str] = Field(default_factory=list)
    market_cap_min: float | None = None
    market_cap_max: float | None = None

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        return [item.strip().upper() for item in value if item.strip()]


class Metrics(BaseModel):
    observed: list[str] = Field(default_factory=list)
    context: list[str] = Field(default_factory=list)
    derived: list[str] = Field(default_factory=list)


class IntelligencePolicy(BaseModel):
    """Machine-readable intelligence policy. The core domain object."""

    version: int = 1
    name: str
    universe: Universe
    metrics: Metrics
    asset_conditions: list[Condition] = Field(default_factory=list)
    logic: Logic = "AND"
    market_context: list[Condition] = Field(default_factory=list)
    min_notify_severity: Severity = "medium"
    actions: list[str] = Field(default_factory=lambda: ["store_event"])
    assumptions: list[str] = Field(default_factory=list)
    summary: str = ""
    interesting_event: str = ""

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name is required")
        return cleaned

    @field_validator("actions")
    @classmethod
    def known_actions(cls, value: list[str]) -> list[str]:
        allowed = {"store_event", "notify_telegram"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"unknown actions: {sorted(unknown)}")
        return value

    def understanding(self) -> dict:
        return {
            "name": self.name,
            "universe": self.universe_label(),
            "signals": self.signal_labels(),
            "interesting_event": self.interesting_event or self.summary,
            "market_context": self.context_label(),
            "behavior": "Monitor every 15 minutes",
            "assumptions": self.assumptions,
            "conditions": [self._condition_label(item) for item in self.asset_conditions],
            "logic": self.logic,
        }

    def universe_label(self) -> str:
        if self.universe.type == "symbols":
            return ", ".join(self.universe.symbols) or "Named assets"
        label = f"Top {self.universe.limit} assets by market cap"
        if self.universe.exclude_stablecoins:
            label += ", stablecoins excluded"
        return label

    def signal_labels(self) -> list[str]:
        mapping = {
            "price_change_24h": "Price",
            "volume_change_24h": "Volume",
            "market_cap_rank": "Market-cap rank",
            "market_cap": "Market cap",
            "fear_greed": "Fear & Greed",
            "rank_improved": "Improving rank",
        }
        names = []
        for group in (self.metrics.observed, self.metrics.derived, self.metrics.context):
            for metric in group:
                label = mapping.get(metric, metric)
                if label not in names:
                    names.append(label)
        return names

    def context_label(self) -> str:
        if any(item.metric == "fear_greed" for item in self.market_context) or "fear_greed" in self.metrics.context:
            return "CMC Fear & Greed (market-wide, not an asset attribute)"
        return "None"

    def _condition_label(self, condition: Condition) -> str:
        return f"{condition.metric} {condition.operator} {condition.value}"


def policy_diff(before: IntelligencePolicy, after: IntelligencePolicy) -> list[dict]:
    changes = []
    before_map = {item.metric: item for item in before.asset_conditions}
    after_map = {item.metric: item for item in after.asset_conditions}
    for metric, new in after_map.items():
        old = before_map.get(metric)
        if old is None:
            changes.append({"metric": metric, "from": None, "to": f"{new.operator} {new.value}"})
        elif old.operator != new.operator or old.value != new.value:
            changes.append(
                {
                    "metric": metric,
                    "from": f"{old.operator} {old.value}",
                    "to": f"{new.operator} {new.value}",
                }
            )
    for metric in before_map:
        if metric not in after_map:
            old = before_map[metric]
            changes.append({"metric": metric, "from": f"{old.operator} {old.value}", "to": None})
    if before.min_notify_severity != after.min_notify_severity:
        changes.append(
            {
                "metric": "min_notify_severity",
                "from": before.min_notify_severity,
                "to": after.min_notify_severity,
            }
        )
    return changes
