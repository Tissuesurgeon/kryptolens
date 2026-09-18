from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from apps.intelligence.job import JobDefinition
from apps.intelligence.job_compiler import compile_job_report
from apps.intelligence.permissions import require_sensitivity
from apps.intelligence.tool_registry import tool_in_registry
from apps.intelligence.tools import DEFAULT_TOOL_PERMISSIONS, tool_allowed
from apps.intelligence.workflow import WorkflowDefinition

JobType = Literal["monitor", "investigate", "research"]
Specialist = Literal["market", "research", "unavailable"]
ApprovalRequirement = Literal["not_required", "pending", "denied"]

ALLOWED_PLAN_STEPS = frozenset(
    {
        "check_btc",
        "load_top_100",
        "load_top_50",
        "calculate_declines",
        "rank_results",
        "compare_quotes",
        "summarize_market",
        "evaluate_policy",
        "watch_trigger",
        "load_listings",
        "get_global_metrics",
        "load_content",
        "relate_news",
        "load_trending",
        "load_gainers",
        "load_new_listings",
        "load_categories",
        "load_historical",
        "load_ohlcv",
        "summarize_regime",
        "detect_anomaly",
        "compare_history",
    }
)
PLAN_LOAD_TOP = re.compile(r"^load_top_\d+$")


def allowed_plan_step(step: str) -> bool:
    return step in ALLOWED_PLAN_STEPS or bool(PLAN_LOAD_TOP.fullmatch(step))


class RepairPolicy(BaseModel):
    max_retries: int = 1


class AgentPlan(BaseModel):
    plan_id: str
    objective: str
    job_type: JobType
    specialist: Specialist
    steps: list[str] = Field(default_factory=list)
    required_inputs: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    verification_requirements: list[str] = Field(default_factory=list)
    completion_criteria: list[str] = Field(default_factory=list)
    repair_policy: RepairPolicy = Field(default_factory=RepairPolicy)
    approval_requirement: ApprovalRequirement = "not_required"
    persistent: bool = False

    @field_validator("steps")
    @classmethod
    def known_steps(cls, value: list[str]) -> list[str]:
        unknown = [step for step in value if not allowed_plan_step(step)]
        if unknown:
            raise ValueError(f"unknown plan step: {unknown[0]}")
        return value


class PlanValidationError(ValueError):
    pass


def job_category(definition: JobDefinition | None) -> str:
    if not definition:
        return "monitor"
    if definition.news_unavailable:
        return "investigate"
    if definition.execution_model == "watch_plus_workflow":
        return "investigate"
    if definition.execution_model == "scheduled":
        return "research"
    if definition.execution_model == "task":
        if "headline" in (definition.purpose or "").lower() or "news" in (definition.purpose or "").lower():
            return "research"
        if "summar" in (definition.purpose or "").lower() or "brief" in (definition.summary or "").lower():
            return "research"
        return "investigate"
    return "monitor"


def validate_agent_plan(plan: AgentPlan, permissions: dict | None = None) -> AgentPlan:
    perms = permissions or dict(DEFAULT_TOOL_PERMISSIONS)
    if plan.specialist == "unavailable":
        if plan.steps or plan.tools:
            raise PlanValidationError("unavailable specialists cannot emit an executable plan")
        return plan
    for tool in plan.tools:
        if not tool_in_registry(tool):
            raise PlanValidationError(f"unknown tool: {tool}")
        if not tool_allowed(perms, tool):
            raise PlanValidationError(f"Lens is not permitted to use {tool}")
        require_sensitivity(tool)
    for step in plan.steps:
        if not allowed_plan_step(step):
            raise PlanValidationError(f"unknown plan step: {step}")
    return plan


def plan_to_workflow(plan: AgentPlan, existing: WorkflowDefinition | None = None) -> WorkflowDefinition:
    validate_agent_plan(plan)
    if existing is not None:
        return existing
    if plan.specialist == "unavailable" or "evaluate_policy" in plan.steps:
        return WorkflowDefinition()
    raise PlanValidationError("no validated workflow is available for this plan")


def build_agent_plan(job: JobDefinition | None, workflow: WorkflowDefinition | None, objective: str = "") -> AgentPlan:
    if job and job.news_unavailable:
        return AgentPlan(
            plan_id=uuid.uuid4().hex,
            objective=job.purpose or "News monitoring isn't available yet.",
            job_type="investigate",
            specialist="unavailable",
            required_inputs=[],
            verification_requirements=[],
            completion_criteria=["honest_refusal"],
            approval_requirement="not_required",
        )

    workflow = workflow or WorkflowDefinition()
    category = job_category(job)
    specialist: Specialist = "research" if category == "research" else "market"
    steps: list[str] = []
    tools: list[str] = []
    verification: list[str] = []
    completion: list[str] = []
    required: list[str] = []

    if workflow.trigger and workflow.trigger.asset:
        asset = workflow.trigger.asset.upper()
        if asset == "BTC":
            steps.append("check_btc")
        else:
            steps.append("watch_trigger")
        if "get_quotes" not in tools:
            tools.append("get_quotes")
        required.append(asset)
        verification.append("btc_trigger_verified" if asset == "BTC" else "trigger_verified")

    limit = 100
    for step in workflow.steps:
        if step.type in {"get_universe", "get_market_data"}:
            limit = step.limit or limit
            steps.append(f"load_top_{limit}")
            if "get_market_listings" not in tools:
                tools.append("get_market_listings")
            verification.append("assets_loaded")
        elif step.type == "get_quotes":
            if "compare_quotes" not in steps:
                steps.append("compare_quotes")
            if "get_quotes" not in tools:
                tools.append("get_quotes")
        elif step.type == "get_content":
            if "load_content" not in steps:
                steps.append("load_content")
            if "get_content" not in tools:
                tools.append("get_content")
            verification.append("headlines_loaded")
        elif step.type == "calculate":
            steps.append("calculate_declines")
            verification.append("decline_calculation_verified")
        elif step.type == "sort":
            steps.append("rank_results")
            verification.append("ranking_verified")
        elif step.type == "get_global_metrics":
            if "get_global_metrics" not in tools:
                tools.append("get_global_metrics")
            if "summarize_market" not in steps:
                steps.append("summarize_market")
        elif step.type == "present" and step.format == "market_summary":
            if "summarize_market" not in steps:
                steps.append("summarize_market")
        elif step.type == "present" and step.format == "news_brief":
            if "relate_news" not in steps:
                steps.append("relate_news")
            verification.append("quotes_loaded")
        elif step.type == "get_quotes_historical":
            if "compare_history" not in steps:
                steps.append("compare_history")
            if "get_quotes_historical" not in tools:
                tools.append("get_quotes_historical")
        elif step.type == "get_ohlcv_historical":
            if "load_ohlcv" not in steps:
                steps.append("load_ohlcv")
            if "get_ohlcv_historical" not in tools:
                tools.append("get_ohlcv_historical")
        elif step.type == "get_trending":
            if "load_trending" not in steps:
                steps.append("load_trending")
            if "get_trending" not in tools:
                tools.append("get_trending")
        elif step.type == "get_gainers_losers":
            if "load_gainers" not in steps:
                steps.append("load_gainers")
            if "get_gainers_losers" not in tools:
                tools.append("get_gainers_losers")
        elif step.type == "get_new_listings":
            if "load_new_listings" not in steps:
                steps.append("load_new_listings")
            if "get_new_listings" not in tools:
                tools.append("get_new_listings")
        elif step.type == "get_categories":
            if "load_categories" not in steps:
                steps.append("load_categories")
            if "get_categories" not in tools:
                tools.append("get_categories")

    if not workflow.steps:
        steps.append("evaluate_policy")
        if "get_market_listings" not in tools:
            tools.append("get_market_listings")

    if "required_fields_present" not in verification:
        verification.append("required_fields_present")

    if any(step.type == "present" and step.format == "ranked_table" for step in workflow.steps):
        completion.append("ranked_result_created")
    elif any(step.type == "present" and step.format == "market_summary" for step in workflow.steps):
        completion.append("report_created")
    elif any(step.type == "present" and step.format == "news_brief" for step in workflow.steps):
        completion.append("news_brief_created")
    else:
        completion.append("result_created")

    return AgentPlan(
        plan_id=uuid.uuid4().hex,
        objective=objective or (job.purpose if job else "Watch the market"),
        job_type=category,  # type: ignore[arg-type]
        specialist=specialist,
        steps=_unique(steps),
        required_inputs=_unique(required),
        tools=_unique(tools),
        capabilities=_capabilities_for(job, workflow),
        verification_requirements=_unique(verification),
        completion_criteria=_unique(completion),
        repair_policy=RepairPolicy(max_retries=1),
        approval_requirement="not_required",
        persistent=bool(job and job.is_persistent()),
    )


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


def _capabilities_for(job, workflow) -> list[str]:
    names: list[str] = ["market"]
    if workflow and any(step.type in {"get_quotes_historical", "get_ohlcv_historical"} for step in workflow.steps):
        names.append("historical")
    if workflow and any(step.type in {"get_trending", "get_gainers_losers", "get_new_listings"} for step in workflow.steps):
        names.append("discovery")
    if job and job.execution_model == "watch_plus_workflow":
        names.extend(["reaction", "anomaly"])
    if job and job.execution_model == "scheduled":
        names.append("regime")
    if job and job.execution_model in {"watch"}:
        names.append("anomaly")
    return _unique(names)


def _apply_capability_steps(plan: AgentPlan) -> None:
    mapping = {
        "historical": ("compare_history", "get_quotes_historical"),
        "discovery": ("load_trending", "get_trending"),
        "regime": ("summarize_regime", "get_fear_and_greed"),
        "anomaly": ("detect_anomaly", "get_quotes"),
        "reaction": ("load_listings", "get_market_listings"),
    }
    for name in plan.capabilities:
        step, tool = mapping.get(name, ("", ""))
        if step and step not in plan.steps:
            plan.steps.append(step)
        if tool and tool not in plan.tools:
            plan.tools.append(tool)


class ChiefAgent:
    """Plans from an understood job. Does not interpret language and does not call CMC."""

    def plan_from_text(
        self,
        text: str,
        provider=None,
        current_policy=None,
        current_job: JobDefinition | None = None,
        current_workflow: WorkflowDefinition | None = None,
    ) -> tuple[AgentPlan, dict]:
        report = compile_job_report(
            text,
            provider=provider,
            current_policy=current_policy,
            current_job=current_job,
            current_workflow=current_workflow,
        )
        plan = build_agent_plan(report["job"], report["workflow"], report["job"].purpose)
        validate_agent_plan(plan, report.get("tool_permissions"))
        if report["workflow"]:
            plan_to_workflow(plan, report["workflow"])
        return plan, report

    def plan_from_version(self, version) -> AgentPlan:
        job = version.as_job()
        workflow = version.as_workflow()
        plan = build_agent_plan(job, workflow, (job.purpose if job else version.source_intent))
        report = version.compile_report_json or {}
        if report.get("capabilities"):
            plan.capabilities = list(report["capabilities"])
        from apps.intelligence.capabilities import required_tools

        extra = required_tools(None, plan.capabilities)
        plan.tools = _unique(list(plan.tools) + extra)
        _apply_capability_steps(plan)
        validate_agent_plan(plan, version.tool_permissions())
        plan_to_workflow(plan, workflow)
        return plan

    def plan_from_task(self, task, report: dict) -> AgentPlan:
        plan = build_agent_plan(report["job"], report["workflow"], task.objective or report["job"].purpose)
        plan.capabilities = list(task.capabilities or report.get("capabilities") or plan.capabilities)
        plan.persistent = task.mode == "work"
        from apps.intelligence.capabilities import required_tools

        extra = required_tools(task, plan.capabilities)
        plan.tools = _unique(list(plan.tools) + extra)
        _apply_capability_steps(plan)
        validate_agent_plan(plan, report.get("tool_permissions"))
        if report.get("workflow"):
            plan_to_workflow(plan, report["workflow"])
        return plan
