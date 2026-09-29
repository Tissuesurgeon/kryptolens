"""Turn a ClarifiedTask + CapabilityPlan into the existing job / workflow / policy report."""

from __future__ import annotations

from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.compiler import extract_listing_limit, infer_you_asked
from apps.intelligence.job import JobDefinition
from apps.intelligence.job_compiler import workflow_from_task
from apps.intelligence.policy import IntelligencePolicy
from apps.intelligence.tools import DEFAULT_TOOL_PERMISSIONS
from apps.intelligence.workflow import WorkflowDefinition, WorkflowStep, WorkflowTrigger


def compile_from_task(
    task: ClarifiedTask,
    *,
    capability_plan=None,
    current_policy: IntelligencePolicy | None = None,
    current_job: JobDefinition | None = None,
    current_workflow: WorkflowDefinition | None = None,
    provider=None,
) -> dict:
    """Pack a validated task and its capability plan into job, workflow, and policy.

    This does not re-read the user's sentence. Callers that only have text use
    compile_message, which understands first.
    """
    from apps.intelligence.research.task import ResearchTask

    if isinstance(task, ResearchTask):
        task = task.to_clarified()
    text = _text_from_task(task)
    workflow = None
    if capability_plan is not None and getattr(capability_plan, "workflow", None) is not None:
        planned = capability_plan.workflow
        if planned.steps or planned.trigger:
            workflow = planned
    if workflow is None:
        workflow = workflow_from_task(task)

    policy = _policy_from_task(task, text)
    job = _job_from_task_and_workflow(task, workflow, text)
    _apply_task_trigger(job, workflow, task)
    job.steps_explained = workflow.explained_steps()

    listings = (task.scope.universe or "").startswith("top") or task.task_type in {
        "watch_plus_investigate",
        "scheduled_brief",
    }
    if task.scope.assets and not listings and task.action not in {"rank_gains", "rank_declines"}:
        policy = policy.model_copy(
            update={
                "universe": policy.universe.model_copy(
                    update={"type": "symbols", "symbols": list(task.scope.assets)}
                )
            }
        )

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
    report["capabilities"] = list(task.capabilities or getattr(capability_plan, "capabilities", None) or [])
    if capability_plan is not None:
        report["capability_plan"] = capability_plan.model_dump(mode="json")
        if getattr(capability_plan, "capabilities", None):
            report["capabilities"] = list(capability_plan.capabilities)
    report["tool_permissions"] = dict(DEFAULT_TOOL_PERMISSIONS)
    _ = current_policy, current_job, current_workflow, provider
    return report


def compile_message(
    text: str,
    *,
    provider=None,
    current_policy: IntelligencePolicy | None = None,
    current_job: JobDefinition | None = None,
    current_workflow: WorkflowDefinition | None = None,
    research_context=None,
    pending: dict | None = None,
) -> dict:
    """Understand a message, plan it once, then pack the existing job infrastructure."""
    from apps.intelligence.conversation_agent import ConversationAgent
    from apps.intelligence.research.planner import ResearchPlanner
    from apps.intelligence.research.task import ResearchTask

    turn = ConversationAgent.understand(
        text,
        provider=provider,
        current_job=current_job,
        pending=pending,
        research_context=research_context,
    )
    research_task = None
    if turn.research:
        research_task = ResearchTask.model_validate(turn.research)
    elif turn.task is not None:
        research_task = ResearchTask.from_clarified(turn.task)
    if turn.status != "ready" or research_task is None:
        return {
            "policy": current_policy,
            "job": None,
            "workflow": current_workflow,
            "clarification": turn.question,
            "turn": turn,
            "research_task": research_task.model_dump(mode="json") if research_task else {},
        }
    research_plan, capability_plan = ResearchPlanner().plan(research_task, research_context)
    report = compile_from_task(
        research_task,
        capability_plan=capability_plan,
        current_policy=current_policy,
        current_job=current_job,
        current_workflow=current_workflow,
        provider=provider,
    )
    report["research_plan"] = research_plan.model_dump(mode="json")
    report["research_task"] = research_task.model_dump(mode="json")
    report["turn"] = turn
    return report


def _text_from_task(task: ClarifiedTask) -> str:
    """Use the understood task. A follow-up sentence must not replace its assets."""
    assets = [str(asset) for asset in task.scope.assets if asset]
    source = task.source_text or ""
    if assets and not any(asset.lower() in source.lower() for asset in assets):
        named = ", ".join(assets)
        return f"{task.objective or source} ({named})".strip()
    return source or task.objective or ""


def compile_task_or_text(
    text: str,
    task: ClarifiedTask | None = None,
    **kwargs,
) -> dict:
    if task and task.status == "ready":
        return compile_from_task(task, **kwargs)
    from apps.intelligence.job_compiler import compile_job_report

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


def _job_from_task_and_workflow(task: ClarifiedTask, workflow: WorkflowDefinition, text: str) -> JobDefinition:
    persistent = task.mode == "work"
    if _task_is_reaction(task):
        execution_model = "watch_plus_workflow"
        routine_kind = "event_triggered"
    elif task.task_type == "scheduled_brief":
        execution_model = "scheduled"
        routine_kind = "scheduled"
    elif persistent:
        execution_model = "watch"
        routine_kind = "event_triggered"
    else:
        execution_model = "task"
        routine_kind = None
    trigger = workflow.trigger
    trigger_summary = ""
    if trigger and trigger.asset:
        trigger_summary = f"{trigger.asset} {trigger.metric} {trigger.operator} {trigger.value}"
    return JobDefinition(
        purpose=task.objective or text,
        summary=text,
        execution_model=execution_model,  # type: ignore[arg-type]
        routine_kind=routine_kind,  # type: ignore[arg-type]
        trigger_summary=trigger_summary,
        workflow_summary=workflow.explained_steps()[-1] if workflow.steps else "",
        you_asked=list(task.you_asked) or ([text.strip()] if text.strip() else []),
        steps_explained=workflow.explained_steps(),
        mode=task.mode,
    )


def _apply_task_trigger(job: JobDefinition, workflow: WorkflowDefinition, task: ClarifiedTask) -> None:
    cond = task.trigger.conditions[0] if task.trigger.conditions else None
    if not cond:
        return
    asset = cond.get("asset") or task.trigger_asset() or (task.scope.assets[0] if task.scope.assets else "")
    if not asset:
        return
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
                symbols=list(task.scope.assets),
                operation=task.scope.window or "30d",
            ),
        )
    return workflow.model_copy(update={"steps": steps})


def _task_is_reaction(task: ClarifiedTask) -> bool:
    if task.task_type == "watch_plus_investigate":
        return True
    if task.action == "investigate_market_reaction":
        return True
    return task.mode == "work" and "reaction" in (task.capabilities or [])
