from __future__ import annotations

import re

from apps.intelligence.compiler import (
    compile_intent_report,
    extract_listing_limit,
    infer_you_asked,
    is_gainers_ask,
    is_losers_ask,
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
    if is_gainers_ask(text) or is_losers_ask(text):
        return _listings_rank(text, policy, "gainers" if is_gainers_ask(text) else "losers")
    if _is_reaction_watch(lowered):
        return _reaction_from_text(text, policy)
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


def _is_reaction_watch(lowered: str) -> bool:
    has_drop = any(word in lowered for word in ("drop", "fall", "fell", "declin"))
    has_percent = bool(re.search(r"\d+(?:\.\d+)?\s*%", lowered))
    has_when = any(stem in lowered for stem in ("when ", "whenever", "every time", "each time"))
    has_universe = bool(re.search(r"\btop\s+\d+\b", lowered)) or (
        "top" in lowered and any(token in lowered for token in ("coins", "assets", "altcoins"))
    ) or ("coin" in lowered and any(stem in lowered for stem in ("find", "show", "rank", "list")))
    has_rank = any(
        word in lowered for word in ("rank", "list", "sort", "biggest", "highest", "find me", "show me")
    )
    if not (has_drop and has_percent):
        return False
    if has_when and has_universe and has_rank:
        return True
    return has_universe and (has_rank or "check" in lowered or "analyze" in lowered)


def _is_btc_reaction(lowered: str) -> bool:
    return _is_reaction_watch(lowered) and ("btc" in lowered or "bitcoin" in lowered)


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


def _reaction_workflow(
    asset: str,
    threshold: float,
    limit: int,
    order: str = "ascending",
    metric: str = "price_change_24h",
    operator: str = "<=",
) -> WorkflowDefinition:
    asset = (asset or "BTC").upper()
    return WorkflowDefinition(
        trigger=WorkflowTrigger(
            type="asset_condition",
            asset=asset,
            metric=metric,
            operator=operator,  # type: ignore[arg-type]
            value=threshold,
        ),
        steps=[
            WorkflowStep(type="get_universe", source="cmc", universe=f"top_{limit}", limit=limit),
            WorkflowStep(
                type="get_market_data",
                fields=["price_change_24h", "market_cap", "cmc_rank"],
            ),
            WorkflowStep(type="calculate", operation="percentage_change"),
            WorkflowStep(type="sort", field="price_change_24h", order=order),  # type: ignore[arg-type]
            WorkflowStep(type="present", format="ranked_table"),
        ],
    )


def _snapshot_workflow(symbols: list[str]) -> WorkflowDefinition:
    return WorkflowDefinition(
        trigger=None,
        steps=[
            WorkflowStep(type="get_quotes", symbols=list(symbols)),
            WorkflowStep(type="present", format="comparison"),
        ],
    )


def _listings_rank_workflow(direction: str, limit: int) -> WorkflowDefinition:
    gains = direction == "gainers"
    return WorkflowDefinition(
        trigger=None,
        steps=[
            WorkflowStep(type="get_universe", source="cmc", universe=f"top_{limit}", limit=limit),
            WorkflowStep(
                type="get_market_data",
                fields=["price_change_24h", "market_cap", "cmc_rank"],
            ),
            WorkflowStep(
                type="filter",
                field="price_change_24h",
                operator=">" if gains else "<",
                value=0,
            ),
            WorkflowStep(type="sort", field="price_change_24h", order="descending" if gains else "ascending"),
            WorkflowStep(type="present", format="ranked_table", operation=direction, limit=10),
        ],
    )


def _asset_reaction(
    text: str,
    policy: IntelligencePolicy,
    asset: str,
    threshold: float,
    limit: int,
    order: str = "ascending",
) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    asset = (asset or "BTC").upper()
    policy = IntelligencePolicy.model_validate(
        {
            **policy.model_dump(),
            "name": f"{asset} Reaction Watcher",
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
            "interesting_event": f"{asset} 24h move <= {threshold}% then rank top {limit} declines",
            "assumptions": list(policy.assumptions)
            + [f"Trigger is {asset} 24h change <= {threshold}%. Ranking uses live listings."],
        }
    )
    workflow = _reaction_workflow(asset, threshold, limit, order=order)
    verb = "Check" if "check" in text.lower() else "Analyze"
    job = JobDefinition(
        purpose=f"Monitor {asset} and analyze how the broader market reacts to major {asset} moves.",
        summary=text.strip(),
        execution_model="watch_plus_workflow",
        routine_kind="event_triggered",
        trigger_summary=f"{asset} 24h change <= {threshold}%",
        workflow_summary=f"Rank top {limit} by 24h decline",
        you_asked=[
            f"When {asset} drops by {abs(threshold)}%",
            f"{verb} the top {limit} coins",
            "Rank them from biggest drop to smallest",
        ],
        steps_explained=workflow.explained_steps(),
    )
    return job, workflow, policy


def _reaction_from_text(text: str, policy: IntelligencePolicy) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    symbols = _extract_symbols(text)
    asset = symbols[0] if symbols else "BTC"
    return _asset_reaction(text, policy, asset, -abs(_percent(text, 2.0)), extract_listing_limit(text))


def _btc_reaction(text: str, policy: IntelligencePolicy) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    return _asset_reaction(text, policy, "BTC", -abs(_percent(text, 2.0)), extract_listing_limit(text))


def _snapshot_symbols(text: str, policy: IntelligencePolicy) -> list[str]:
    mentioned = _extract_symbols(text)
    if mentioned:
        return mentioned[:4]
    symbols = list(policy.universe.symbols or [])
    if symbols:
        return symbols[:4]
    lowered = text.upper()
    for symbol in ("BTC", "ETH", "SOL", "XRP"):
        if re.search(rf"\b{symbol}\b", lowered):
            symbols.append(symbol)
    if "BITCOIN" in lowered and "BTC" not in symbols:
        symbols.append("BTC")
    if "ETHEREUM" in lowered and "ETH" not in symbols:
        symbols.append("ETH")
    return symbols[:4] or ["BTC"]


def _status_now(text: str, policy: IntelligencePolicy) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    symbols = _snapshot_symbols(text, policy)
    policy = policy.model_copy(
        update={
            "name": f"{symbols[0]} now",
            "universe": policy.universe.model_copy(update={"type": "symbols", "symbols": symbols}),
            "asset_conditions": [],
            "interesting_event": f"Live {', '.join(symbols)} snapshot",
        }
    )
    workflow = _snapshot_workflow(symbols)
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
    mentioned = _extract_symbols(text)
    symbols = list(mentioned or policy.universe.symbols or [])
    if len(symbols) < 2:
        lowered = text.upper()
        for symbol in ("BTC", "ETH", "SOL", "XRP"):
            if re.search(rf"\b{symbol}\b", lowered) and symbol not in symbols:
                symbols.append(symbol)
        symbols = symbols[:4] or ["BTC", "ETH"]
    policy = policy.model_copy(
        update={
            "name": " vs ".join(symbols),
            "universe": policy.universe.model_copy(update={"type": "symbols", "symbols": symbols}),
        }
    )
    workflow = _snapshot_workflow(symbols)
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


def _listings_rank(
    text: str, policy: IntelligencePolicy, direction: str = "gainers"
) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    limit = policy.universe.limit if policy.universe.type == "listings" else extract_listing_limit(text)
    gains = direction == "gainers"
    order = "descending" if gains else "ascending"
    label = "gain" if gains else "decline"
    policy = policy.model_copy(
        update={
            "name": "Highest 24h gains" if gains else "Biggest 24h declines",
            "universe": policy.universe.model_copy(
                update={"type": "listings", "limit": limit, "exclude_stablecoins": True, "symbols": []}
            ),
            "asset_conditions": [],
            "interesting_event": f"Live top {limit} ranked by 24h {label}",
        }
    )
    workflow = _listings_rank_workflow(direction, limit)
    job = JobDefinition(
        purpose=f"Rank top listings by 24h {label} from live CMC data.",
        summary=text.strip(),
        execution_model="task",
        routine_kind=None,
        trigger_summary="",
        workflow_summary=f"Rank top {limit} by 24h {label}",
        you_asked=[text.strip()],
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


def workflow_from_task(task) -> WorkflowDefinition:
    """Build a workflow from ClarifiedTask fields. Does not re-parse natural language."""
    from apps.intelligence.clarified_task import ClarifiedTask

    if not isinstance(task, ClarifiedTask):
        task = ClarifiedTask.model_validate(task)
    limit = task.scope.listing_limit or 100
    assets = list(task.scope.assets)
    if task.task_type == "news_brief":
        return WorkflowDefinition(
            trigger=None,
            steps=[
                WorkflowStep(type="get_content", source="news", symbols=list(assets), limit=20),
                WorkflowStep(type="get_quotes", symbols=list(assets)),
                WorkflowStep(type="present", format="news_brief"),
            ],
        )
    if task.task_type == "scheduled_brief":
        return WorkflowDefinition(
            trigger=WorkflowTrigger(type="scheduled"),
            steps=[
                WorkflowStep(type="get_universe", source="cmc", universe=f"top_{limit}", limit=limit),
                WorkflowStep(type="get_market_data", fields=["price_change_24h", "market_cap"]),
                WorkflowStep(type="get_global_metrics"),
                WorkflowStep(type="aggregate", operation="mean"),
                WorkflowStep(type="present", format="market_summary"),
            ],
        )
    if _task_is_reaction(task):
        cond = task.trigger.conditions[0] if task.trigger.conditions else {}
        asset = task.trigger_asset() or (assets[0] if assets else "BTC")
        threshold = cond.get("value", -2.0)
        try:
            threshold = float(threshold)
        except (TypeError, ValueError):
            threshold = -2.0
        metric = cond.get("metric") or "price_change_24h"
        operator = cond.get("operator") or "<="
        return _reaction_workflow(asset, threshold, limit, metric=metric, operator=operator)
    if task.mode == "work":
        cond = task.trigger.conditions[0] if task.trigger.conditions else None
        asset = task.trigger_asset() or (assets[0] if assets else "BTC")
        trigger = None
        if cond and cond.get("value") is not None:
            trigger = WorkflowTrigger(
                type="asset_condition",
                asset=asset,
                metric=cond.get("metric") or "price_change_24h",
                operator=cond.get("operator") or "<=",
                value=float(cond.get("value")),
            )
        steps = []
        if asset:
            steps = [
                WorkflowStep(type="get_quotes", symbols=[asset]),
                WorkflowStep(type="present", format="comparison"),
            ]
        return WorkflowDefinition(trigger=trigger, steps=steps)
    if task.action in {"rank_gains", "rank_declines"} or task.requested_output == "ranked_table":
        direction = "gainers" if task.action == "rank_gains" else "losers"
        return _listings_rank_workflow(direction, limit)
    if task.action == "market_summary" or ("regime" in (task.capabilities or []) and not assets):
        return WorkflowDefinition(
            trigger=None,
            steps=[
                WorkflowStep(type="get_global_metrics"),
                WorkflowStep(type="get_fear_and_greed"),
                WorkflowStep(type="get_universe", source="cmc", universe=f"top_{limit}", limit=limit),
                WorkflowStep(type="get_market_data", fields=["price_change_24h", "market_cap"]),
                WorkflowStep(type="aggregate", operation="mean"),
                WorkflowStep(type="present", format="market_summary"),
            ],
        )
    symbols = assets[:4] or ["BTC"]
    if len(assets) >= 2:
        symbols = assets[:4]
    workflow = _snapshot_workflow(symbols)
    if task.scope.window or "historical" in task.capabilities:
        steps = list(workflow.steps)
        insert_at = next((i for i, step in enumerate(steps) if step.type == "present"), len(steps))
        steps.insert(
            insert_at,
            WorkflowStep(
                type="get_quotes_historical",
                symbols=list(symbols),
                operation=task.scope.window or "30d",
            ),
        )
        workflow = workflow.model_copy(update={"steps": steps})
    return workflow


def _task_is_reaction(task) -> bool:
    if task.task_type == "watch_plus_investigate":
        return True
    if task.action == "investigate_market_reaction":
        return True
    if task.mode == "work" and "reaction" in (task.capabilities or []):
        return True
    return False
