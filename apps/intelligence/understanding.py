"""LLM understands the user message. Chief Agent plans from that understanding. No CMC here."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from apps.intelligence.compiler import _extract_json, extract_listing_limit
from apps.intelligence.job import ExecutionModel, JobDefinition, RoutineKind
from apps.intelligence.llm import HeuristicProvider
from apps.intelligence.policy import IntelligencePolicy, Operator
from apps.intelligence.workflow import WorkflowDefinition, WorkflowStep, WorkflowTrigger

Kind = Literal["snapshot", "compare", "watch", "watch_plus_workflow", "scheduled", "news", "edit"]
PresentFormat = Literal["comparison", "ranked_table", "market_summary"]

UNDERSTAND_SYSTEM = """You understand a crypto-market request for KryptoLens.
Return ONLY valid JSON. No markdown. No tools. No file edits.

Decide what THIS user message wants. Do not classify by keywords alone.

Kinds:
- snapshot: how a coin is doing now/today, current price, status. One-shot. No watch.
- compare: compare coins right now. One-shot.
- watch: notify when a named coin crosses a threshold the user actually stated.
- watch_plus_workflow: when a coin moves, then rank/analyze a listings universe (top N).
- scheduled: every morning / recurring market brief.
- news: news, headlines, articles, what news is affecting the market. Fetch CMC Content Latest and relate headlines to live quotes. Do not compile a price-threshold watch. Do not edit the current job unless they are changing a watch.
- edit: they are changing an existing standing job (stricter, different top N, instead of).

{
  "you_asked": ["the user's request in their words, not only a ticker"],
  "assumptions": ["only real interpretation assumptions"],
  "kind": "snapshot",
  "name": "short name",
  "purpose": "one sentence",
  "symbols": ["BTC"],
  "listing_limit": null,
  "execution_model": "task",
  "routine_kind": null,
  "trigger": null,
  "present": "comparison",
  "news_unavailable": false
}

trigger example (only if the user stated a when/threshold):
{"asset": "BTC", "metric": "price_change_24h", "operator": "<=", "value": -2}

Rules:
- CoinMarketCap quotes, listings, and Content Latest headlines only. No on-chain, wallets, or invented market numbers.
- snapshot and compare: execution_model=task, routine_kind=null, trigger=null. Do not invent a percent.
- "how is bitcoin doing on the market today" is snapshot for BTC, not a 5% watch.
- "what news is affecting the crypto market today" is news: headlines plus live quotes, not a top-100 watch and not an edit.
- If they did not state a percent or when-condition, kind is snapshot or compare, never watch.
- you_asked must keep the user's wording.
- If a current job is provided and this message is a new one-shot question, use snapshot/compare. Do not treat it as an edit of the standing watch unless they are changing that watch.
"""


class UnderstandingTrigger(BaseModel):
    asset: str = "BTC"
    metric: str = "price_change_24h"
    operator: Operator = "<="
    value: float | None = None


class Understanding(BaseModel):
    you_asked: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    kind: Kind = "snapshot"
    name: str = "Job"
    purpose: str = ""
    symbols: list[str] = Field(default_factory=list)
    listing_limit: int | None = None
    execution_model: ExecutionModel = "task"
    routine_kind: RoutineKind | None = None
    trigger: UnderstandingTrigger | None = None
    present: PresentFormat | None = "comparison"
    news_unavailable: bool = False


def provider_is_llm(provider) -> bool:
    return provider is not None and not isinstance(provider, HeuristicProvider)


def understand_with_llm(
    text: str,
    provider,
    current_policy: IntelligencePolicy | None = None,
    current_job: JobDefinition | None = None,
    current_workflow: WorkflowDefinition | None = None,
) -> Understanding:
    prompt = UNDERSTAND_SYSTEM + "\n\nUser message:\n" + text.strip()
    if current_job:
        prompt += "\n\nCurrent job JSON:\n" + current_job.model_dump_json()
    if current_workflow:
        prompt += "\n\nCurrent workflow JSON:\n" + current_workflow.model_dump_json()
    if current_policy:
        prompt += "\n\nCurrent policy JSON:\n" + current_policy.model_dump_json()
    raw = provider.generate(prompt, kind="understand")
    data = _extract_json(raw)
    understanding = Understanding.model_validate(data)
    return _normalize(understanding, text)


def _normalize(understanding: Understanding, text: str) -> Understanding:
    from apps.intelligence.job_compiler import is_news_request

    if is_news_request(text) or understanding.kind == "news":
        understanding.kind = "news"
        understanding.news_unavailable = False
        understanding.execution_model = "task"
        understanding.routine_kind = None
        understanding.trigger = None
        if not understanding.you_asked:
            understanding.you_asked = [text.strip()]
        understanding.symbols = [item.strip().upper() for item in understanding.symbols if item.strip()]
        return understanding
    if understanding.kind in {"watch", "watch_plus_workflow"} and understanding.trigger is None:
        understanding.kind = "snapshot"
        understanding.execution_model = "task"
        understanding.routine_kind = None
    if understanding.kind in {"snapshot", "compare"}:
        understanding.execution_model = "task"
        understanding.routine_kind = None
        understanding.trigger = None
        understanding.news_unavailable = False
    if understanding.kind == "scheduled":
        understanding.execution_model = "scheduled"
        understanding.routine_kind = "scheduled"
    if understanding.kind == "watch":
        understanding.execution_model = "watch"
        understanding.routine_kind = "event_triggered"
    if understanding.kind == "watch_plus_workflow":
        understanding.execution_model = "watch_plus_workflow"
        understanding.routine_kind = "event_triggered"
        if understanding.listing_limit is None:
            understanding.listing_limit = extract_listing_limit(text)
    if not understanding.you_asked:
        understanding.you_asked = [text.strip()]
    understanding.symbols = [item.strip().upper() for item in understanding.symbols if item.strip()]
    return understanding


def materialize_understanding(
    text: str,
    understanding: Understanding,
    current_job: JobDefinition | None = None,
    current_workflow: WorkflowDefinition | None = None,
    current_policy: IntelligencePolicy | None = None,
) -> tuple[JobDefinition, WorkflowDefinition, IntelligencePolicy]:
    from apps.intelligence.job_compiler import _apply_edit, _news_job

    if understanding.kind == "news":
        report = _news_job(text)
        return report["job"], report["workflow"], report["policy"]
    if understanding.kind == "edit" and current_job and current_workflow:
        policy = current_policy or policy_from_understanding(understanding, text)
        return _apply_edit(text, policy, current_job, current_workflow)
    policy = policy_from_understanding(understanding, text)
    if understanding.kind == "snapshot":
        return _snapshot(text, understanding, policy)
    if understanding.kind == "compare":
        return _compare(text, understanding, policy)
    if understanding.kind == "scheduled":
        return _scheduled(text, understanding, policy)
    if understanding.kind == "watch_plus_workflow":
        return _watch_plus(text, understanding, policy)
    return _watch(text, understanding, policy)


def policy_from_understanding(understanding: Understanding, text: str) -> IntelligencePolicy:
    symbols = list(understanding.symbols)
    if understanding.kind in {"snapshot", "compare", "watch"} or (
        understanding.kind == "watch_plus_workflow" and symbols and not understanding.listing_limit
    ):
        if not symbols:
            symbols = ["BTC"]
        universe = {
            "type": "symbols",
            "limit": 100,
            "exclude_stablecoins": True,
            "symbols": symbols,
        }
    else:
        limit = understanding.listing_limit or extract_listing_limit(text)
        universe = {
            "type": "listings",
            "limit": limit,
            "exclude_stablecoins": True,
            "symbols": [],
        }
    conditions = []
    trigger = understanding.trigger
    if trigger and understanding.kind not in {"snapshot", "compare"} and trigger.value is not None:
        conditions.append(
            {"metric": trigger.metric, "operator": trigger.operator, "value": trigger.value}
        )
    name = (understanding.name or "").strip() or "Job"
    return IntelligencePolicy.model_validate(
        {
            "version": 1,
            "name": name[:80],
            "universe": universe,
            "metrics": {"observed": ["price_change_24h"], "context": [], "derived": []},
            "asset_conditions": conditions,
            "logic": "AND",
            "market_context": [],
            "min_notify_severity": "medium",
            "actions": ["store_event", "notify_telegram"],
            "assumptions": list(understanding.assumptions),
            "summary": understanding.purpose or text.strip(),
            "interesting_event": understanding.purpose or text.strip(),
        }
    )


def _asked(understanding: Understanding, text: str) -> list[str]:
    return list(understanding.you_asked) or [text.strip()]


def _snapshot(text: str, understanding: Understanding, policy: IntelligencePolicy):
    symbols = policy.universe.symbols or understanding.symbols or ["BTC"]
    workflow = WorkflowDefinition(
        trigger=None,
        steps=[
            WorkflowStep(type="get_quotes", symbols=symbols),
            WorkflowStep(type="present", format=understanding.present or "comparison"),
        ],
    )
    job = JobDefinition(
        purpose=understanding.purpose or f"Report how {' and '.join(symbols)} is doing from live CMC quotes.",
        summary=text.strip(),
        execution_model="task",
        routine_kind=None,
        workflow_summary=f"Live quotes for {', '.join(symbols)}",
        you_asked=_asked(understanding, text),
        steps_explained=workflow.explained_steps(),
    )
    return job, workflow, policy


def _compare(text: str, understanding: Understanding, policy: IntelligencePolicy):
    symbols = policy.universe.symbols or understanding.symbols or ["BTC", "ETH"]
    if len(symbols) < 2:
        symbols = (symbols + ["BTC", "ETH"])[:2]
    policy = policy.model_copy(
        update={"universe": policy.universe.model_copy(update={"type": "symbols", "symbols": symbols})}
    )
    workflow = WorkflowDefinition(
        trigger=None,
        steps=[
            WorkflowStep(type="get_quotes", symbols=symbols),
            WorkflowStep(type="present", format="comparison"),
        ],
    )
    job = JobDefinition(
        purpose=understanding.purpose or f"Compare {' and '.join(symbols)} from live CMC quotes.",
        summary=text.strip(),
        execution_model="task",
        routine_kind=None,
        workflow_summary=f"Compare {', '.join(symbols)}",
        you_asked=_asked(understanding, text),
        steps_explained=workflow.explained_steps(),
    )
    return job, workflow, policy


def _scheduled(text: str, understanding: Understanding, policy: IntelligencePolicy):
    limit = policy.universe.limit if policy.universe.type == "listings" else understanding.listing_limit or 100
    policy = policy.model_copy(
        update={"universe": policy.universe.model_copy(update={"type": "listings", "limit": limit})}
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
        purpose=understanding.purpose or "Summarize overnight crypto using live CMC listings.",
        summary=text.strip(),
        execution_model="scheduled",
        routine_kind="scheduled",
        trigger_summary="Every morning",
        workflow_summary="Market summary of top listings",
        you_asked=_asked(understanding, text),
        steps_explained=workflow.explained_steps(),
    )
    return job, workflow, policy


def _watch(text: str, understanding: Understanding, policy: IntelligencePolicy):
    trigger = None
    if understanding.trigger and understanding.trigger.value is not None:
        trigger = WorkflowTrigger(
            type="asset_condition",
            asset=understanding.trigger.asset,
            metric=understanding.trigger.metric,
            operator=understanding.trigger.operator,
            value=float(understanding.trigger.value),
        )
    workflow = WorkflowDefinition(trigger=trigger, steps=[])
    cond = policy.asset_conditions[0] if policy.asset_conditions else None
    asset = (policy.universe.symbols or ["BTC"])[0]
    job = JobDefinition(
        purpose=understanding.purpose or policy.summary or text.strip(),
        summary=text.strip(),
        execution_model="watch",
        routine_kind="event_triggered",
        trigger_summary=f"{asset} {cond.metric} {cond.operator} {cond.value}" if cond else "",
        you_asked=_asked(understanding, text),
        steps_explained=workflow.explained_steps() or ["Notify when the trigger fires"],
    )
    return job, workflow, policy


def _watch_plus(text: str, understanding: Understanding, policy: IntelligencePolicy):
    limit = understanding.listing_limit or policy.universe.limit or extract_listing_limit(text)
    trigger = understanding.trigger
    threshold = float(trigger.value) if trigger and trigger.value is not None else -2.0
    asset = (trigger.asset if trigger else "BTC") or "BTC"
    operator = trigger.operator if trigger else "<="
    metric = trigger.metric if trigger else "price_change_24h"
    workflow = WorkflowDefinition(
        trigger=WorkflowTrigger(
            type="asset_condition",
            asset=asset,
            metric=metric,
            operator=operator,
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
        purpose=understanding.purpose or "Monitor the trigger and analyze how the market reacts.",
        summary=text.strip(),
        execution_model="watch_plus_workflow",
        routine_kind="event_triggered",
        trigger_summary=f"{asset} {metric} {operator} {threshold}",
        workflow_summary=f"Rank top {limit} by 24h decline",
        you_asked=_asked(understanding, text),
        steps_explained=workflow.explained_steps(),
    )
    policy = policy.model_copy(
        update={
            "universe": policy.universe.model_copy(update={"type": "listings", "limit": limit, "symbols": []}),
        }
    )
    return job, workflow, policy
