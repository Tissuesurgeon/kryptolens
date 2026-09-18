"""Chief Agent's validated capability plan. Registries stay the authority."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from apps.intelligence.capabilities import CAPABILITIES
from apps.intelligence.clarified_task import ClarifiedTask, TaskScope
from apps.intelligence.tool_registry import registry_names, tool_in_registry
from apps.intelligence.tools import TOOL_GROUPS
from apps.intelligence.workflow import ALLOWED_STEP_TYPES, WorkflowDefinition

CAPABILITY_TOOL_GROUPS = {
    "market": ("market", "context"),
    "anomaly": ("market", "discovery"),
    "reaction": ("market", "context"),
    "historical": ("historical",),
    "discovery": ("discovery", "market"),
    "regime": ("context", "market"),
}

STEP_TOOLS = {
    "get_universe": "get_market_listings",
    "get_market_data": "get_market_listings",
    "get_quotes": "get_quotes",
    "get_quotes_historical": "get_quotes_historical",
    "get_ohlcv_historical": "get_ohlcv_historical",
    "get_global_metrics": "get_global_metrics",
    "get_fear_and_greed": "get_fear_and_greed",
    "get_content": "get_content",
    "get_trending": "get_trending",
    "get_gainers_losers": "get_gainers_losers",
    "get_new_listings": "get_new_listings",
    "get_categories": "get_categories",
}


class CapabilityPlanError(ValueError):
    pass


class CapabilityPlan(BaseModel):
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    workflow: WorkflowDefinition = Field(default_factory=WorkflowDefinition)
    reason: str = ""
    verification_requirements: list[str] = Field(default_factory=list)
    persistent: bool = False

    @field_validator("capabilities")
    @classmethod
    def known_capabilities(cls, value: list[str]) -> list[str]:
        unknown = [name for name in value if name not in CAPABILITIES]
        if unknown:
            raise CapabilityPlanError(f"unknown capability: {unknown[0]}")
        return list(dict.fromkeys(value))

    @field_validator("tools")
    @classmethod
    def known_tools(cls, value: list[str]) -> list[str]:
        unknown = [name for name in value if not tool_in_registry(name)]
        if unknown:
            raise CapabilityPlanError(f"unknown tool: {unknown[0]}")
        invented = [name for name in value if name not in registry_names()]
        if invented:
            raise CapabilityPlanError(f"invented tool: {invented[0]}")
        return list(dict.fromkeys(value))

    @field_validator("workflow", mode="before")
    @classmethod
    def coerce_workflow(cls, value: Any) -> Any:
        if value in (None, {}):
            return WorkflowDefinition()
        if isinstance(value, WorkflowDefinition):
            return value
        if isinstance(value, dict):
            steps = value.get("steps") or []
            if not isinstance(steps, list):
                raise CapabilityPlanError("invalid workflow: steps must be a list")
            for step in steps:
                step_type = (step or {}).get("type") if isinstance(step, dict) else getattr(step, "type", None)
                if step_type not in ALLOWED_STEP_TYPES:
                    raise CapabilityPlanError(f"invalid workflow step: {step_type}")
            try:
                return WorkflowDefinition.model_validate(value)
            except CapabilityPlanError:
                raise
            except Exception as exc:
                raise CapabilityPlanError(f"invalid workflow: {exc}") from exc
        raise CapabilityPlanError("invalid workflow structure")

    @model_validator(mode="after")
    def tools_match_capabilities(self):
        allowed = _allowed_tools_for(self.capabilities)
        for step in self.workflow.steps:
            tool = STEP_TOOLS.get(step.type)
            if tool:
                allowed.add(tool)
        for tool in self.tools:
            if tool not in allowed:
                raise CapabilityPlanError(f"tool unavailable to selected capabilities: {tool}")
        return self

    def to_agent_plan(self, task: ClarifiedTask | None = None, objective: str = ""):
        from apps.intelligence.agent import AgentPlan, RepairPolicy, build_agent_plan, _unique

        job = None
        workflow = self.workflow
        plan = build_agent_plan(job, workflow, objective or (task.objective if task else "") or self.reason)
        plan.capabilities = list(self.capabilities or plan.capabilities)
        plan.tools = _unique(list(self.tools or plan.tools))
        plan.verification_requirements = _unique(
            list(self.verification_requirements or plan.verification_requirements)
        )
        plan.persistent = self.persistent if task is None else task.mode == "work"
        if not plan.specialist:
            plan.specialist = "research" if "historical" in plan.capabilities else "market"
        plan.repair_policy = plan.repair_policy or RepairPolicy()
        return plan


def _allowed_tools_for(capabilities: list[str]) -> set[str]:
    allowed: set[str] = set()
    probes = (
        ClarifiedTask(capabilities=list(capabilities)),
        ClarifiedTask(
            capabilities=list(capabilities),
            task_type="watch_plus_investigate",
            scope=TaskScope(universe="top_100", listing_limit=100),
        ),
        ClarifiedTask(
            capabilities=list(capabilities),
            task_type="scheduled_brief",
            scope=TaskScope(universe="top_100"),
        ),
    )
    for name in capabilities:
        cap = CAPABILITIES.get(name)
        if not cap:
            continue
        for probe in probes:
            allowed.update(cap.required_tools(probe))
        for group in CAPABILITY_TOOL_GROUPS.get(name, ()):
            allowed.update(TOOL_GROUPS.get(group, ()))
    return allowed


def tools_from_workflow(workflow: WorkflowDefinition | None) -> list[str]:
    tools: list[str] = []
    if not workflow:
        return tools
    if workflow.trigger and workflow.trigger.asset and "get_quotes" not in tools:
        tools.append("get_quotes")
    for step in workflow.steps:
        tool = STEP_TOOLS.get(step.type)
        if tool and tool not in tools:
            tools.append(tool)
    return tools


def verification_for_workflow(workflow: WorkflowDefinition | None, task: ClarifiedTask | None = None) -> list[str]:
    names: list[str] = []
    if workflow and workflow.trigger and workflow.trigger.asset:
        names.append("verify_trigger")
    if workflow and any(step.type == "sort" for step in workflow.steps):
        names.append("verify_rank_order")
    if workflow and any(step.type == "calculate" for step in workflow.steps):
        names.append("verify_percentage_calculations")
    if task and task.mode == "ask":
        names.append("required_fields_present")
    elif "required_fields_present" not in names:
        names.append("required_fields_present")
    return list(dict.fromkeys(names))
