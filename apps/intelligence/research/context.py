"""Research context lives on Lens.context_json. It is not a table and not a price cache."""

from __future__ import annotations

import re
import uuid

from pydantic import BaseModel, Field

from apps.intelligence.clarified_task import ClarifiedTask, TaskScope, TaskTrigger, TurnResult
from apps.intelligence.compiler import _extract_symbols
from apps.intelligence.research.finding import Finding
from apps.intelligence.research.task import ResearchTask

ADD_RE = re.compile(r"\b(?:now\s+)?(?:add|include|also)\s+([A-Za-z]{2,12})\b", re.I)
TOP_RE = re.compile(r"\btop\s+(\d+)\b", re.I)
SAME_PERIOD = ("same period", "same window", "same timeframe", "same time frame", "use the same period")
DEEPER = ("go deeper", "dig deeper", "more detail", "look closer")
UNUSUAL = ("was that unusual", "is that unusual", "was this unusual", "is this unusual", "is that unusual?")


class ResearchContext(BaseModel):
    session_id: str = ""
    active_entities: list[str] = Field(default_factory=list)
    universe: str = ""
    timeframe: str = ""
    metrics: list[str] = Field(default_factory=list)
    comparisons: list[str] = Field(default_factory=list)
    current_question: str = ""
    recent_findings: list[Finding] = Field(default_factory=list)
    current_task: dict | None = None
    research_plan: dict | None = None

    def ensure_session(self) -> str:
        if not self.session_id:
            self.session_id = uuid.uuid4().hex[:12]
        return self.session_id

    @classmethod
    def from_json(cls, payload: dict | None) -> ResearchContext:
        raw = (payload or {}).get("research") or {}
        if not raw:
            return cls()
        try:
            return cls.model_validate(raw)
        except Exception:
            return cls()

    def dump_into(self, payload: dict | None) -> dict:
        context = dict(payload or {})
        self.ensure_session()
        context["research"] = self.model_dump(mode="json")
        return context

    def apply_task(self, task: ResearchTask, plan: dict | None = None) -> None:
        self.ensure_session()
        task.ensure_id()
        if not task.id:
            task.id = self.session_id
        self.current_task = task.model_dump(mode="json")
        self.current_question = task.objective or task.source_text
        if task.assets:
            self.active_entities = list(dict.fromkeys(task.assets))
        if task.universe:
            self.universe = task.universe
        if task.window:
            self.timeframe = task.window
        if task.metrics:
            self.metrics = list(task.metrics)
        if task.comparisons:
            self.comparisons = list(task.comparisons)
        if plan is not None:
            self.research_plan = plan

    def remember_finding(self, finding: Finding) -> None:
        self.recent_findings = ([finding] + list(self.recent_findings))[:8]


def resolve_follow_up(text: str, context: ResearchContext | None) -> TurnResult | None:
    if not context or not context.current_task:
        return None
    raw = (text or "").strip()
    if not raw:
        return None
    lowered = " ".join(raw.lower().split())
    try:
        base = ResearchTask.model_validate(context.current_task)
    except Exception:
        return None
    if _is_fresh_request(lowered):
        return None

    inherited = base.model_copy(deep=True)
    inherited.follow_up = True
    inherited.source_text = raw
    inherited.you_asked = list(dict.fromkeys(list(inherited.you_asked) + [raw]))
    inherited.status = "ready"
    inherited.question = ""
    inherited.pending_field = ""

    add = ADD_RE.search(raw)
    if add:
        symbol = add.group(1).upper()
        if symbol in {"THE", "THIS", "THAT", "SAME", "PERIOD", "TOP"}:
            symbol = ""
        if symbol and symbol not in inherited.assets:
            inherited.assets = list(inherited.assets) + [symbol]
        inherited.objective = _objective(inherited)
        return _ready_turn(inherited)

    if any(phrase in lowered for phrase in SAME_PERIOD):
        inherited.window = inherited.window or context.timeframe
        if not inherited.window:
            question = "Which period should I use?"
            inherited.status = "needs_input"
            inherited.question = question
            inherited.pending_field = "window"
            return TurnResult(status="needs_input", question=question, task=inherited.to_clarified())
        inherited.objective = _objective(inherited)
        return _ready_turn(inherited)

    if any(phrase in lowered for phrase in UNUSUAL):
        assets = inherited.assets or list(context.active_entities)
        inherited.assets = assets
        inherited.capabilities = list(dict.fromkeys(list(inherited.capabilities) + ["anomaly", "market"]))
        inherited.action = "report"
        inherited.objective = f"Check whether the latest {' and '.join(assets) or 'move'} is unusual."
        inherited.assumptions = list(inherited.assumptions) + ["Unusual uses the criteria already on this research task."]
        return _ready_turn(inherited)

    if any(phrase in lowered for phrase in DEEPER):
        inherited.capabilities = list(dict.fromkeys(["historical", "market"] + list(inherited.capabilities)))
        if not inherited.window:
            inherited.window = context.timeframe or "30d"
        inherited.objective = f"Go deeper on {' and '.join(inherited.assets) or 'the current assets'}."
        return _ready_turn(inherited)

    top = TOP_RE.search(lowered)
    if top and len(lowered.split()) <= 6:
        inherited.listing_limit = int(top.group(1))
        inherited.universe = "top_100" if inherited.listing_limit else inherited.universe
        inherited.objective = _objective(inherited)
        return _ready_turn(inherited)

    if lowered in {"it", "that", "this", "the same", "same"}:
        question = "What should I do with the current research?"
        inherited.status = "needs_input"
        inherited.question = question
        inherited.pending_field = "follow_up"
        return TurnResult(status="needs_input", question=question, task=inherited.to_clarified())

    symbols = _extract_symbols(raw)
    if not symbols and not _recognized_research(lowered):
        question = "I am still on the current research. What should I change?"
        inherited.status = "needs_input"
        inherited.question = question
        inherited.pending_field = "follow_up"
        inherited.assets = list(context.active_entities or inherited.assets)
        return TurnResult(status="needs_input", question=question, task=inherited.to_clarified())
    return None


def _ready_turn(task: ResearchTask) -> TurnResult:
    clarified = task.to_clarified()
    clarified.status = "ready"
    return TurnResult(status="ready", task=clarified)


def _objective(task: ResearchTask) -> str:
    assets = " and ".join(task.assets) if task.assets else "the current assets"
    window = f" over {task.window}" if task.window else ""
    limit = f", top {task.listing_limit}" if task.listing_limit else ""
    return f"Continue research on {assets}{window}{limit}."


def _is_fresh_request(lowered: str) -> bool:
    if any(phrase in lowered for phrase in ("how is", "how are", "what is", "what's", "compare", "watch", "when ")):
        if "unusual" in lowered and "that" in lowered:
            return False
        return True
    if "gain" in lowered or "loser" in lowered or "highest" in lowered:
        return True
    return False


def _recognized_research(lowered: str) -> bool:
    return any(
        token in lowered
        for token in ("compare", "watch", "drop", "gain", "rank", "news", "morning", "brief", "quote")
    )


def clarified_with_context(task: ClarifiedTask, context: ResearchContext) -> ClarifiedTask:
    if task.scope.assets or not context.active_entities:
        return task
    task.scope = TaskScope(
        assets=list(context.active_entities),
        universe=task.scope.universe or context.universe,
        window=task.scope.window or context.timeframe,
        listing_limit=task.scope.listing_limit,
    )
    if context.current_task and not task.trigger.conditions:
        previous = context.current_task.get("trigger_conditions") or []
        if previous and task.follow_up:
            task.trigger = TaskTrigger(conditions=list(previous))
    return task
