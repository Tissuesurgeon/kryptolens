from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from apps.intelligence.policy import Operator

TriggerType = Literal["asset_condition", "manual", "scheduled"]
StepType = Literal[
    "get_universe",
    "get_market_data",
    "get_quotes",
    "get_quotes_historical",
    "get_ohlcv_historical",
    "get_global_metrics",
    "get_fear_and_greed",
    "get_content",
    "get_trending",
    "get_gainers_losers",
    "get_new_listings",
    "get_categories",
    "calculate",
    "sort",
    "filter",
    "aggregate",
    "present",
]
ALLOWED_STEP_TYPES = set(StepType.__args__)
PresentFormat = Literal["ranked_table", "market_summary", "comparison", "news_brief"]


class WorkflowTrigger(BaseModel):
    type: TriggerType
    asset: str | None = None
    metric: str = "price_change_24h"
    operator: Operator = "<="
    value: float | None = None


class WorkflowStep(BaseModel):
    type: StepType
    source: str | None = None
    universe: str | None = None
    limit: int | None = Field(default=None, ge=1, le=500)
    symbols: list[str] = Field(default_factory=list)
    fields: list[str] = Field(default_factory=list)
    operation: str | None = None
    field: str | None = None
    order: Literal["ascending", "descending"] | None = None
    operator: Operator | None = None
    value: float | bool | int | None = None
    relative_to: str | None = None
    format: PresentFormat | None = None

    @field_validator("type")
    @classmethod
    def known_type(cls, value: str) -> str:
        if value not in ALLOWED_STEP_TYPES:
            raise ValueError(f"unknown workflow step: {value}")
        return value


class WorkflowDefinition(BaseModel):
    trigger: WorkflowTrigger | None = None
    steps: list[WorkflowStep] = Field(default_factory=list)

    @model_validator(mode="after")
    def reject_empty_unknown(self):
        for step in self.steps:
            if step.type not in ALLOWED_STEP_TYPES:
                raise ValueError(f"unknown workflow step: {step.type}")
        return self

    def explained_steps(self) -> list[str]:
        labels = []
        if self.trigger and self.trigger.type == "asset_condition":
            labels.append(
                f"Watch {self.trigger.asset or 'asset'} until "
                f"{self.trigger.metric} {self.trigger.operator} {self.trigger.value}"
            )
        for step in self.steps:
            labels.append(_step_label(step))
        return labels


def _step_label(step: WorkflowStep) -> str:
    if step.type == "get_universe":
        return f"Retrieve {step.universe or ('top_' + str(step.limit or 100))}"
    if step.type == "get_market_data":
        return "Retrieve market observations"
    if step.type == "get_quotes":
        return "Retrieve quotes for " + ", ".join(step.symbols or [])
    if step.type == "calculate":
        return f"Calculate {step.operation or 'values'}"
    if step.type == "sort":
        direction = "largest decline first" if step.order == "ascending" else "sort"
        return f"Sort by {step.field or 'price_change_24h'} ({direction})"
    if step.type == "filter":
        if step.relative_to:
            return f"Keep assets that moved more than {step.relative_to}"
        return f"Filter {step.field} {step.operator} {step.value}"
    if step.type == "present":
        return f"Return {step.format or 'ranked_table'}"
    if step.type == "get_global_metrics":
        return "Retrieve global market metrics"
    if step.type == "get_fear_and_greed":
        return "Retrieve Fear & Greed"
    if step.type == "get_content":
        tagged = ", ".join(step.symbols) if step.symbols else "the market"
        return f"Retrieve CoinMarketCap headlines for {tagged}"
    if step.type == "get_quotes_historical":
        return "Retrieve historical quotes"
    if step.type == "get_ohlcv_historical":
        return "Retrieve historical OHLCV"
    if step.type == "get_trending":
        return "Retrieve trending assets"
    if step.type == "get_gainers_losers":
        return "Retrieve gainers and losers"
    if step.type == "get_new_listings":
        return "Retrieve new listings"
    if step.type == "get_categories":
        return "Retrieve market categories"
    if step.type == "aggregate":
        return f"Aggregate {step.operation or 'summary'}"
    return step.type


def validate_workflow_dict(data: dict[str, Any]) -> WorkflowDefinition:
    steps = data.get("steps") or []
    for step in steps:
        step_type = (step or {}).get("type")
        if step_type not in ALLOWED_STEP_TYPES:
            raise ValueError(f"unknown workflow step: {step_type}")
        if step_type in {"eval", "exec", "code", "http"}:
            raise ValueError("arbitrary code is not allowed")
    return WorkflowDefinition.model_validate(data)
