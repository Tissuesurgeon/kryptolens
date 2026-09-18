"""Turn a ClarifiedTask into the existing job / workflow / policy report."""

from __future__ import annotations

from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.compiler import extract_listing_limit, infer_you_asked, is_gainers_ask, is_losers_ask
from apps.intelligence.job import JobDefinition
from apps.intelligence.job_compiler import (
    _btc_reaction,
    _compare_now,
    _event_watch,
    _listings_rank,
    _morning_brief,
    _news_job,
    _status_now,
    compile_job_report,
)
from apps.intelligence.policy import IntelligencePolicy
from apps.intelligence.tools import DEFAULT_TOOL_PERMISSIONS
from apps.intelligence.workflow import WorkflowDefinition, WorkflowStep, WorkflowTrigger


def compile_from_task(
    task: ClarifiedTask,
    *,
    current_policy: IntelligencePolicy | None = None,
    current_job: JobDefinition | None = None,
    current_workflow: WorkflowDefinition | None = None,
    provider=None,
) -> dict:
    text = task.source_text or task.objective or ""
    if task.task_type == "news_brief":
        report = _news_job(text)
    elif task.task_type == "scheduled_brief":
        policy = current_policy or _policy_from_task(task, text)
        job, workflow, policy = _morning_brief(text, policy)
        report = _pack(job, workflow, policy, text)
    elif task.task_type == "watch_plus_investigate":
        policy = current_policy or _policy_from_task(task, text)
        synthetic = text if "top" in text.lower() and "%" in text else _synthetic_reaction(task)
        job, workflow, policy = _btc_reaction(synthetic, policy)
        _apply_task_trigger(job, workflow, task)
        report = _pack(job, workflow, policy, text)
    elif task.mode == "work":
        policy = current_policy or _policy_from_task(task, text)
        if task.action == "investigate_market_reaction":
            job, workflow, policy = _btc_reaction(_synthetic_reaction(task), policy)
            _apply_task_trigger(job, workflow, task)
        else:
            job, workflow, policy = _event_watch(text or task.objective, policy)
            _apply_task_trigger(job, workflow, task)
        report = _pack(job, workflow, policy, text)
    elif is_gainers_ask(text) or is_losers_ask(text):
        policy = _policy_from_task(task, text)
        job, workflow, policy = _listings_rank(
            text or task.objective,
            policy,
            "gainers" if is_gainers_ask(text) else "losers",
        )
        report = _pack(job, workflow, policy, text)
    elif task.scope.window or "historical" in task.capabilities:
        policy = _policy_from_task(task, text)
        job, workflow, policy = _compare_now(text or task.objective, policy)
        workflow = _with_historical(workflow, task)
        report = _pack(job, workflow, policy, text)
    elif len(task.scope.assets) >= 2 and "compare" in (text or "").lower():
        policy = _policy_from_task(task, text)
        job, workflow, policy = _compare_now(text, policy)
        report = _pack(job, workflow, policy, text)
    else:
        policy = _policy_from_task(task, text)
        job, workflow, policy = _status_now(text or task.objective, policy)
        report = _pack(job, workflow, policy, text)

    job = report["job"]
    job.mode = task.mode
    job.you_asked = list(task.you_asked) or job.you_asked or [text.strip()]
    if task.assumptions:
        policy = report["policy"].model_copy(update={"assumptions": list(task.assumptions)})
        report["policy"] = policy
        report["assumptions"] = list(task.assumptions)
    if task.mode == "ask":
        job.execution_model = "task"
        job.routine_kind = None
        job.mode = "ask"
    else:
        job.mode = "work"
        if not job.routine_kind:
            job.routine_kind = "scheduled" if task.task_type == "scheduled_brief" else "event_triggered"
        if job.execution_model == "task":
            job.execution_model = "scheduled" if task.task_type == "scheduled_brief" else "watch"
    report["job"] = job
    report["you_asked"] = job.you_asked
    report["clarified_task"] = task.model_dump(mode="json")
    report["capabilities"] = list(task.capabilities)
    report["tool_permissions"] = dict(DEFAULT_TOOL_PERMISSIONS)
    _ = current_job, current_workflow, provider
    return report


def compile_task_or_text(
    text: str,
    task: ClarifiedTask | None = None,
    **kwargs,
) -> dict:
    if task and task.status == "ready":
        return compile_from_task(task, **kwargs)
    return compile_job_report(text, **kwargs)


def _pack(job: JobDefinition, workflow: WorkflowDefinition, policy: IntelligencePolicy, text: str) -> dict:
    return {
        "policy": policy,
        "job": job,
        "workflow": workflow,
        "you_asked": job.you_asked or infer_you_asked(text, policy),
        "assumptions": list(policy.assumptions),
        "clarification": None,
        "confidence": 0.9,
        "used_heuristic": True,
        "tool_permissions": dict(DEFAULT_TOOL_PERMISSIONS),
        "routine_kind": job.routine_kind,
    }


def _policy_from_task(task: ClarifiedTask, text: str) -> IntelligencePolicy:
    assets = list(task.scope.assets)
    limit = task.scope.listing_limit or extract_listing_limit(text) or 100
    if task.scope.universe.startswith("top") or task.task_type in {"scheduled_brief", "watch_plus_investigate"}:
        universe = {"type": "listings", "limit": limit, "exclude_stablecoins": True, "symbols": []}
    else:
        universe = {
            "type": "symbols" if assets else "listings",
            "limit": limit,
            "exclude_stablecoins": True,
            "symbols": assets or [],
        }
    conditions = []
    for item in task.trigger.conditions:
        if item.get("value") is None:
            continue
        conditions.append(
            {"metric": item.get("metric") or "price_change_24h", "operator": item.get("operator") or "<=", "value": item.get("value")}
        )
    return IntelligencePolicy.model_validate(
        {
            "version": 1,
            "name": (task.objective or text or "Job")[:80],
            "universe": universe,
            "metrics": {"observed": ["price_change_24h"], "context": [], "derived": []},
            "asset_conditions": conditions,
            "logic": task.trigger.logic or "AND",
            "market_context": [],
            "min_notify_severity": "medium",
            "actions": ["store_event", "notify_telegram"],
            "assumptions": list(task.assumptions),
            "summary": task.objective or text,
            "interesting_event": task.objective or text,
        }
    )


def _synthetic_reaction(task: ClarifiedTask) -> str:
    cond = task.trigger.conditions[0] if task.trigger.conditions else {}
    value = cond.get("value", -2)
    asset = cond.get("asset") or (task.scope.assets[0] if task.scope.assets else "BTC")
    limit = task.scope.listing_limit or 100
    return f"When {asset} drops by {abs(float(value))}%, check the top {limit} coins and rank their declines."


def _apply_task_trigger(job: JobDefinition, workflow: WorkflowDefinition, task: ClarifiedTask) -> None:
    cond = task.trigger.conditions[0] if task.trigger.conditions else None
    if not cond:
        return
    asset = cond.get("asset") or (task.scope.assets[0] if task.scope.assets else "BTC")
    metric = cond.get("metric") or "price_change_24h"
    operator = cond.get("operator") or "<="
    value = cond.get("value")
    workflow.trigger = WorkflowTrigger(
        type="asset_condition",
        asset=asset,
        metric=metric,
        operator=operator,
        value=value,
    )
    job.trigger_summary = f"{asset} {metric} {operator} {value}"


def _with_historical(workflow: WorkflowDefinition, task: ClarifiedTask) -> WorkflowDefinition:
    steps = list(workflow.steps)
    if not any(step.type == "get_quotes_historical" for step in steps):
        insert_at = next((i for i, step in enumerate(steps) if step.type == "present"), len(steps))
        steps.insert(
            insert_at,
            WorkflowStep(
                type="get_quotes_historical",
                symbols=list(task.scope.assets) or ["BTC"],
                operation=task.scope.window or "30d",
            ),
        )
    return workflow.model_copy(update={"steps": steps})
