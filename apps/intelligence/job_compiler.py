from __future__ import annotations

import re

from apps.intelligence.compiler import (
    compile_intent_report,
    extract_listing_limit,
    infer_you_asked,
    is_now_status,
    _extract_symbols,
)
from apps.intelligence.job import JobDefinition
from apps.intelligence.policy import IntelligencePolicy
from apps.intelligence.tools import DEFAULT_TOOL_PERMISSIONS
from apps.intelligence.workflow import WorkflowDefinition, WorkflowStep, WorkflowTrigger

NEWS_PHRASES = (
    "news watcher",
    "track crypto news",
    "watch news",
    "crypto news",
    "monitor news",
    "news monitoring",
    "what news",
    "any news",
    "latest news",
    "market news",
    "news affecting",
    "news about",
)
NEWS_SKIP = (
    "ignore news",
    "without news",
    "no news",
    "not news",
)


def is_news_request(text: str) -> bool:
    lowered = text.lower()
    if any(phrase in lowered for phrase in NEWS_SKIP):
        return False
    if any(phrase in lowered for phrase in NEWS_PHRASES):
        return True
    if "headline" in lowered or "headlines" in lowered:
        return True
    return "news" in lowered


def compile_job_report(
    text: str,
    provider=None,
    current_policy: IntelligencePolicy | None = None,
    current_job: JobDefinition | None = None,
    current_workflow: WorkflowDefinition | None = None,
) -> dict:
    if is_news_request(text):
        return _news_job(text)

    from apps.intelligence.llm import get_provider
    from apps.intelligence.understanding import materialize_understanding, provider_is_llm, understand_with_llm

    provider = provider or get_provider()
    if provider_is_llm(provider):
        try:
            understanding = understand_with_llm(
                text,
                provider,
                current_policy=current_policy,
                current_job=current_job,
                current_workflow=current_workflow,
            )
            job, workflow, policy = materialize_understanding(
                text,
                understanding,
                current_job=current_job,
                current_workflow=current_workflow,
                current_policy=current_policy,
            )
            return {
                "policy": policy,
                "you_asked": job.you_asked or infer_you_asked(text, policy),
                "assumptions": list(policy.assumptions),
                "clarification": "News monitoring isn't available yet." if job.news_unavailable else None,
                "confidence": 0.94,
                "used_heuristic": False,
                "job": job,
                "workflow": workflow,
                "tool_permissions": dict(DEFAULT_TOOL_PERMISSIONS),
                "routine_kind": job.routine_kind,
            }
        except Exception:
            pass

    report = compile_intent_report(text, provider=provider, current_policy=current_policy)
    policy = report["policy"]
    job, workflow, policy = infer_job_and_workflow(
        text,
        policy,
        current_job=current_job,
        current_workflow=current_workflow,
    )
    if job.you_asked:
        report["you_asked"] = job.you_asked
    else:
        job.you_asked = list(report.get("you_asked") or infer_you_asked(text, policy))
    if job.news_unavailable:
        report["clarification"] = "News monitoring isn't available yet."
    return {
        **report,
        "policy": policy,
        "job": job,
        "workflow": workflow,
        "tool_permissions": dict(DEFAULT_TOOL_PERMISSIONS),
        "routine_kind": job.routine_kind,
    }


def infer_job_and_workflow(
    text: str,
    policy: IntelligencePolicy,
    current_job: JobDefinition | None = None,
    current_workflow: WorkflowDefinition | None = None,
) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    lowered = text.lower()
    if is_news_request(text):
        report = _news_job(text)
        return report["job"], report["workflow"], report["policy"]
    if current_job and current_workflow and _is_edit(lowered):
        return _apply_edit(text, policy, current_job, current_workflow)
    if is_now_status(text):
        return _status_now(text, policy)
    if _is_btc_reaction(lowered):
        return _btc_reaction(text, policy)
    if _is_compare_now(lowered):
        return _compare_now(text, policy)
    if _is_scheduled_brief(lowered):
        return _morning_brief(text, policy)
    if _is_event_only(lowered, policy):
        return _event_watch(text, policy)
    return _default_watch(text, policy)


def _is_edit(lowered: str) -> bool:
    return any(
        phrase in lowered
        for phrase in (
            "stricter",
            "instead of",
            "only show",
            "only include",
            "ignore",
            "every morning",
            "dropped more than",
            "change top",
            "use top",
        )
    ) or bool(re.search(r"\btop\s+\d+\b", lowered))


def _is_btc_reaction(lowered: str) -> bool:
    has_btc = "btc" in lowered or "bitcoin" in lowered
    has_drop = any(word in lowered for word in ("drop", "fall", "fell", "declin"))
    has_universe = bool(re.search(r"\btop\s+\d+\b", lowered)) or (
        "top" in lowered and any(token in lowered for token in ("coins", "assets", "altcoins"))
    )
    has_rank = any(word in lowered for word in ("rank", "list", "sort", "biggest"))
    return has_btc and has_drop and has_universe and (has_rank or "check" in lowered or "analyze" in lowered)


def _is_compare_now(lowered: str) -> bool:
    if "compare" not in lowered:
        return False
    if any(word in lowered for word in ("when", "every time", "whenever", "each time")):
        return False
    return True


def _is_scheduled_brief(lowered: str) -> bool:
    return "every morning" in lowered or ("summarize" in lowered and "morning" in lowered)


def _is_event_only(lowered: str, policy: IntelligencePolicy) -> bool:
    return policy.universe.type == "symbols" and "top" not in lowered


def _percent(text: str, default: float) -> float:
    found = re.findall(r"(\d+(?:\.\d+)?)\s*%", text)
    return float(found[0]) if found else default


def _btc_reaction(text: str, policy: IntelligencePolicy) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    threshold = -abs(_percent(text, 2.0))
    limit = extract_listing_limit(text)
    policy = IntelligencePolicy.model_validate(
        {
            **policy.model_dump(),
            "name": "BTC Reaction Watcher",
            "universe": {
                "type": "listings",
                "limit": limit,
                "exclude_stablecoins": True,
                "symbols": [],
            },
            "metrics": {
                "observed": ["price_change_24h", "market_cap", "market_cap_rank"],
                "context": [],
                "derived": [],
            },
            "asset_conditions": [],
            "market_context": [],
            "summary": text.strip(),
            "interesting_event": f"BTC 24h move <= {threshold}% then rank top {limit} declines",
            "assumptions": list(policy.assumptions)
            + [f"Trigger is BTC 24h change <= {threshold}%. Ranking uses live listings."],
        }
    )
    workflow = WorkflowDefinition(
        trigger=WorkflowTrigger(
            type="asset_condition",
            asset="BTC",
            metric="price_change_24h",
            operator="<=",
            value=threshold,
        ),
        steps=[
            WorkflowStep(type="get_universe", source="cmc", universe=f"top_{limit}", limit=limit),
            WorkflowStep(
                type="get_market_data",
                fields=["price_change_24h", "market_cap", "cmc_rank"],
            ),
            WorkflowStep(type="calculate", operation="percentage_change"),
            WorkflowStep(type="sort", field="price_change_24h", order="ascending"),
            WorkflowStep(type="present", format="ranked_table"),
        ],
    )
    job = JobDefinition(
        purpose="Monitor Bitcoin and analyze how the broader market reacts to major BTC moves.",
        summary=text.strip(),
        execution_model="watch_plus_workflow",
        routine_kind="event_triggered",
        trigger_summary=f"BTC 24h change <= {threshold}%",
        workflow_summary=f"Rank top {limit} by 24h decline",
        you_asked=[
            f"When BTC drops by {abs(threshold)}%",
            f"{'Check' if 'check' in text.lower() else 'Analyze'} the top {limit} coins",
            "Rank them from biggest drop to smallest",
        ],
        steps_explained=workflow.explained_steps(),
    )
    return job, workflow, policy


def _status_now(text: str, policy: IntelligencePolicy) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    symbols = list(policy.universe.symbols or [])
    if not symbols:
        lowered = text.upper()
        for symbol in ("BTC", "ETH", "SOL", "XRP"):
            if symbol in lowered:
                symbols.append(symbol)
        if "BITCOIN" in text.upper() and "BTC" not in symbols:
            symbols.append("BTC")
        if "ETHEREUM" in text.upper() and "ETH" not in symbols:
            symbols.append("ETH")
        symbols = symbols[:4] or ["BTC"]
    policy = policy.model_copy(
        update={
            "name": f"{symbols[0]} now",
            "universe": policy.universe.model_copy(update={"type": "symbols", "symbols": symbols}),
            "asset_conditions": [],
            "interesting_event": f"Live {', '.join(symbols)} snapshot",
        }
    )
    workflow = WorkflowDefinition(
        trigger=None,
        steps=[
            WorkflowStep(type="get_quotes", symbols=symbols),
            WorkflowStep(type="present", format="comparison"),
        ],
    )
    names = " and ".join(symbols)
    job = JobDefinition(
        purpose=f"Report how {names} is doing from live CMC quotes.",
        summary=text.strip(),
        execution_model="task",
        routine_kind=None,
        trigger_summary="",
        workflow_summary=f"Live quotes for {', '.join(symbols)}",
        you_asked=[text.strip()],
        steps_explained=workflow.explained_steps(),
    )
    return job, workflow, policy


def _compare_now(text: str, policy: IntelligencePolicy) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    symbols = policy.universe.symbols or ["BTC", "ETH"]
    if len(symbols) < 2:
        lowered = text.upper()
        for symbol in ("BTC", "ETH", "SOL", "XRP"):
            if symbol in lowered and symbol not in symbols:
                symbols.append(symbol)
        symbols = symbols[:4] or ["BTC", "ETH"]
    policy = policy.model_copy(
        update={
            "name": " vs ".join(symbols),
            "universe": policy.universe.model_copy(update={"type": "symbols", "symbols": symbols}),
        }
    )
    workflow = WorkflowDefinition(
        trigger=None,
        steps=[
            WorkflowStep(type="get_quotes", symbols=symbols),
            WorkflowStep(type="present", format="comparison"),
        ],
    )
    job = JobDefinition(
        purpose=f"Compare {' and '.join(symbols)} from live CMC quotes.",
        summary=text.strip(),
        execution_model="task",
        routine_kind=None,
        workflow_summary=f"Compare {', '.join(symbols)}",
        you_asked=[f"Compare {' and '.join(symbols)} right now"],
        steps_explained=workflow.explained_steps(),
    )
    return job, workflow, policy


def _morning_brief(text: str, policy: IntelligencePolicy) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    limit = policy.universe.limit if policy.universe.type == "listings" else 100
    policy = policy.model_copy(
        update={
            "name": "Morning Market Brief",
            "universe": policy.universe.model_copy(update={"type": "listings", "limit": limit}),
        }
    )
    workflow = WorkflowDefinition(
        trigger=WorkflowTrigger(type="scheduled"),
        steps=[
            WorkflowStep(type="get_universe", source="cmc", universe=f"top_{limit}", limit=limit),
            WorkflowStep(type="get_market_data", fields=["price_change_24h", "market_cap"]),
            WorkflowStep(type="get_global_metrics"),
            WorkflowStep(type="aggregate", operation="mean"),
            WorkflowStep(type="present", format="market_summary"),
        ],
    )
    job = JobDefinition(
        purpose="Summarize overnight crypto using live CMC listings.",
        summary=text.strip(),
        execution_model="scheduled",
        routine_kind="scheduled",
        trigger_summary="Every morning",
        workflow_summary="Market summary of top listings",
        you_asked=["Every morning summarize major crypto changes"],
        steps_explained=workflow.explained_steps(),
    )
    return job, workflow, policy


def _event_watch(text: str, policy: IntelligencePolicy) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    cond = policy.asset_conditions[0] if policy.asset_conditions else None
    asset = (policy.universe.symbols or ["BTC"])[0]
    trigger = None
    if cond:
        trigger = WorkflowTrigger(
            type="asset_condition",
            asset=asset,
            metric=cond.metric,
            operator=cond.operator,
            value=float(cond.value) if not isinstance(cond.value, bool) else cond.value,
        )
    workflow = WorkflowDefinition(trigger=trigger, steps=[])
    job = JobDefinition(
        purpose=policy.summary or policy.interesting_event or text.strip(),
        summary=text.strip(),
        execution_model="watch",
        routine_kind="event_triggered",
        trigger_summary=f"{asset} {cond.metric} {cond.operator} {cond.value}" if cond else "",
        workflow_summary="",
        you_asked=infer_you_asked(text, policy),
        steps_explained=["Notify when the trigger fires"],
    )
    return job, workflow, policy


def _default_watch(text: str, policy: IntelligencePolicy) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    workflow = WorkflowDefinition(trigger=None, steps=[])
    job = JobDefinition(
        purpose=policy.summary or policy.interesting_event or text.strip(),
        summary=text.strip(),
        execution_model="watch",
        routine_kind="event_triggered",
        trigger_summary=policy.interesting_event,
        you_asked=infer_you_asked(text, policy),
        steps_explained=["Evaluate the Intelligence Policy against live CMC listings"],
    )
    return job, workflow, policy


def _apply_edit(
    text: str,
    policy: IntelligencePolicy,
    current_job: JobDefinition,
    current_workflow: WorkflowDefinition,
) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    lowered = text.lower()
    workflow = current_workflow.model_copy(deep=True)
    job = current_job.model_copy(deep=True)
    data = policy.model_dump()

    if re.search(r"\btop\s+\d+\b", lowered):
        limit = extract_listing_limit(text)
        data["universe"]["limit"] = limit
        for step in workflow.steps:
            if step.type in {"get_universe", "get_market_data"}:
                step.limit = limit
            if step.universe and step.universe.startswith("top_"):
                step.universe = f"top_{limit}"
        if "rank" in (job.workflow_summary or "").lower() or "decline" in (job.workflow_summary or "").lower():
            job.workflow_summary = f"Rank top {limit} by 24h decline"

    if "dropped more than" in lowered or "more than btc" in lowered:
        if not any(step.type == "filter" and step.relative_to == "BTC" for step in workflow.steps):
            present = next((i for i, step in enumerate(workflow.steps) if step.type == "present"), len(workflow.steps))
            workflow.steps.insert(
                present,
                WorkflowStep(type="filter", field="price_change_24h", relative_to="BTC", operator="<"),
            )
        job.workflow_summary = (job.workflow_summary or "") + " · only steeper than BTC"

    if "every morning" in lowered:
        job.execution_model = "scheduled"
        job.routine_kind = "scheduled"
        job.trigger_summary = "Every morning"

    if any(word in lowered for word in ("stricter", "only show", "raise")) and current_workflow.trigger:
        trigger = workflow.trigger
        if trigger and trigger.value is not None and not isinstance(trigger.value, bool):
            trigger.value = float(trigger.value) * 1.5 if trigger.value > 0 else float(trigger.value) * 1.5

    policy = IntelligencePolicy.model_validate(data)
    job.summary = text.strip()
    job.steps_explained = workflow.explained_steps()
    job.you_asked = infer_you_asked(text, policy)
    return job, workflow, policy


def _news_is_standing(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in ("watch news", "news watcher", "monitor news", "track news", "keep me updated")
    )


def _news_job(text: str) -> dict:
    symbols = _extract_symbols(text)
    standing = _news_is_standing(text)
    universe_symbols = list(symbols)
    universe = {
        "type": "symbols" if universe_symbols else "listings",
        "limit": 100,
        "exclude_stablecoins": True,
        "symbols": universe_symbols,
    }
    policy = IntelligencePolicy.model_validate(
        {
            "version": 1,
            "name": "Market news" if not standing else "News watch",
            "universe": universe,
            "metrics": {"observed": ["price_change_24h"], "context": [], "derived": []},
            "asset_conditions": [],
            "summary": text.strip(),
            "interesting_event": "CoinMarketCap headline related to a live quote",
            "assumptions": [
                "Headlines come from CoinMarketCap Content Latest (News/Headlines).",
                "Prices come from live CoinMarketCap quotes only.",
            ],
        }
    )
    workflow = WorkflowDefinition(
        trigger=None,
        steps=[
            WorkflowStep(type="get_content", source="news", symbols=list(symbols), limit=20),
            WorkflowStep(type="get_quotes", symbols=list(symbols)),
            WorkflowStep(type="present", format="news_brief"),
        ],
    )
    asked = [text.strip()] if text.strip() else ["Market news"]
    job = JobDefinition(
        purpose="Relate CoinMarketCap headlines to live quotes.",
        summary=text.strip(),
        execution_model="scheduled" if standing else "task",
        routine_kind="interval" if standing else None,
        news_unavailable=False,
        workflow_summary="Headlines plus live quotes",
        you_asked=asked,
        steps_explained=workflow.explained_steps(),
    )
    return {
        "policy": policy,
        "job": job,
        "workflow": workflow,
        "tool_permissions": dict(DEFAULT_TOOL_PERMISSIONS),
        "routine_kind": job.routine_kind,
        "you_asked": job.you_asked,
        "assumptions": list(policy.assumptions),
        "clarification": None,
        "confidence": 1.0,
        "used_heuristic": True,
    }


def _news_unavailable(text: str) -> dict:
    return _news_job(text)
