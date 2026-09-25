"""Plans research from a task and context. Does not call CoinMarketCap."""

from __future__ import annotations

from apps.intelligence.capabilities import required_tools
from apps.intelligence.capability_plan import CapabilityPlan, tools_from_workflow, verification_for_workflow
from apps.intelligence.job_compiler import workflow_from_task
from apps.intelligence.research.plan import ResearchPlan
from apps.intelligence.research.task import ResearchTask


class ResearchPlanner:
    """Selects capabilities and tools that already exist. Does not call CMC."""

    def plan(self, task, context=None, report: dict | None = None):
        _ = context
        research_task = task if isinstance(task, ResearchTask) else ResearchTask.from_clarified(task)
        clarified = research_task.to_clarified()
        capabilities = list(clarified.capabilities or _default_capabilities(clarified))
        workflow = workflow_from_task(clarified)
        if report and report.get("workflow") and (report["workflow"].steps or report["workflow"].trigger):
            if not workflow.steps and not workflow.trigger:
                workflow = report["workflow"]
        tools = _unique(required_tools(clarified, capabilities) + tools_from_workflow(workflow))
        reason = _reason(clarified, capabilities)
        verification = verification_for_workflow(workflow, clarified)
        capability_plan = CapabilityPlan(
            capabilities=capabilities,
            tools=tools,
            workflow=workflow,
            reason=reason,
            verification_requirements=verification,
            persistent=clarified.mode == "work",
        )
        research_plan = ResearchPlan.from_capabilities(
            clarified.objective or reason,
            list(capability_plan.capabilities),
            research_task,
        )
        return research_plan, capability_plan


def _default_capabilities(task) -> list[str]:
    names: list[str] = []
    if task.task_type == "watch_plus_investigate" or task.action == "investigate_market_reaction":
        names.extend(["market", "reaction"])
    elif task.task_type == "persistent_monitor":
        names.extend(["anomaly", "market"])
    elif task.task_type == "scheduled_brief":
        names.extend(["market", "regime"])
    else:
        names.append("market")
    if task.scope.window or "historical" in (task.capabilities or []):
        if "historical" not in names:
            names.append("historical")
    if "discovery" in (task.capabilities or []) and "discovery" not in names:
        names.append("discovery")
    return _unique(names)


def _reason(task, capabilities: list[str]) -> str:
    joined = ", ".join(capabilities) or "market"
    asset = task.trigger_asset()
    if asset and "reaction" in capabilities:
        return f"The request requires detecting a {asset} trigger and comparing reactions across the selected universe ({joined})."
    if task.scope.window:
        return f"The request compares live quotes with previous observations ({joined})."
    return f"The request is served by {joined}."


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))
