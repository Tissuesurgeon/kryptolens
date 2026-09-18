from __future__ import annotations

from apps.intelligence.observations import QueryPlan
from apps.intelligence.planner import plan_query
from apps.intelligence.policy import IntelligencePolicy
from apps.intelligence.tools import CMC_TOOL_NAMES, tool_allowed
from apps.intelligence.workflow import WorkflowDefinition


def plan_workflow(policy: IntelligencePolicy, workflow: WorkflowDefinition | None, permissions: dict | None) -> QueryPlan:
    """Extend plan_query with workflow steps. Never invent tools outside the registry."""
    plan = plan_query(policy)
    if not workflow:
        return _permit(plan, permissions)
    endpoints = list(plan.endpoints)
    for step in workflow.steps:
        if step.type in {"get_universe", "get_market_data"} and tool_allowed(permissions, "get_market_listings"):
            if "/v3/cryptocurrency/listings/latest" not in endpoints:
                endpoints.append("/v3/cryptocurrency/listings/latest")
        if step.type == "get_quotes" and tool_allowed(permissions, "get_quotes"):
            if "/v3/cryptocurrency/quotes/latest" not in endpoints:
                endpoints.append("/v3/cryptocurrency/quotes/latest")
        if step.type == "get_global_metrics" and tool_allowed(permissions, "get_global_metrics"):
            if "/v1/global-metrics/quotes/latest" not in endpoints:
                endpoints.append("/v1/global-metrics/quotes/latest")
        if step.type == "get_fear_and_greed" and tool_allowed(permissions, "get_fear_and_greed"):
            if "/v3/fear-and-greed/latest" not in endpoints:
                endpoints.append("/v3/fear-and-greed/latest")
    return _permit(plan.model_copy(update={"endpoints": endpoints}), permissions)


def _permit(plan: QueryPlan, permissions: dict | None) -> QueryPlan:
    allowed_endpoints = []
    mapping = {
        "/v3/cryptocurrency/listings/latest": "get_market_listings",
        "/v3/cryptocurrency/quotes/latest": "get_quotes",
        "/v1/global-metrics/quotes/latest": "get_global_metrics",
        "/v3/fear-and-greed/latest": "get_fear_and_greed",
    }
    for endpoint in plan.endpoints:
        tool = mapping.get(endpoint)
        if tool and tool in CMC_TOOL_NAMES and tool_allowed(permissions, tool):
            allowed_endpoints.append(endpoint)
    return plan.model_copy(update={"endpoints": allowed_endpoints})
