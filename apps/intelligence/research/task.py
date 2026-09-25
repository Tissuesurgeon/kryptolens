"""A research task is the understood request. ClarifiedTask is the compiler adapter."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from apps.intelligence.clarified_task import ClarifiedTask, TaskScope, TaskTrigger

Mode = Literal["ask", "work"]
TaskStatus = Literal["needs_input", "ready"]
TaskType = Literal[
    "one_shot_research",
    "persistent_monitor",
    "scheduled_brief",
    "watch_plus_investigate",
    "news_brief",
]


class ResearchTask(BaseModel):
    id: str = ""
    status: TaskStatus = "ready"
    mode: Mode = "ask"
    task_type: TaskType = "one_shot_research"
    objective: str = ""
    assets: list[str] = Field(default_factory=list)
    universe: str = ""
    window: str = ""
    listing_limit: int | None = None
    metrics: list[str] = Field(default_factory=list)
    comparisons: list[str] = Field(default_factory=list)
    trigger_conditions: list[dict] = Field(default_factory=list)
    action: str = "report"
    requested_output: str = "natural_language_report"
    you_asked: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    question: str = ""
    pending_field: str = ""
    capabilities: list[str] = Field(default_factory=list)
    source_text: str = ""
    news_unavailable: bool = False
    follow_up: bool = False

    def ensure_id(self) -> str:
        if not self.id:
            self.id = uuid.uuid4().hex[:12]
        return self.id

    def to_clarified(self) -> ClarifiedTask:
        return ClarifiedTask(
            status=self.status,
            mode=self.mode,
            task_type=self.task_type,
            objective=self.objective,
            scope=TaskScope(
                assets=list(self.assets),
                universe=self.universe,
                window=self.window,
                listing_limit=self.listing_limit,
            ),
            trigger=TaskTrigger(conditions=list(self.trigger_conditions)),
            action=self.action,
            requested_output=self.requested_output,
            you_asked=list(self.you_asked),
            assumptions=list(self.assumptions),
            question=self.question,
            pending_field=self.pending_field,
            capabilities=list(self.capabilities),
            source_text=self.source_text,
            news_unavailable=self.news_unavailable,
        )

    @classmethod
    def from_clarified(cls, task: ClarifiedTask, *, follow_up: bool = False, session_id: str = "") -> ResearchTask:
        return cls(
            id=session_id,
            status=task.status,
            mode=task.mode,
            task_type=task.task_type,
            objective=task.objective,
            assets=[str(item).upper() for item in task.scope.assets if item],
            universe=task.scope.universe or "",
            window=task.scope.window or "",
            listing_limit=task.scope.listing_limit,
            trigger_conditions=list(task.trigger.conditions or []),
            action=task.action or "report",
            requested_output=task.requested_output or "natural_language_report",
            you_asked=list(task.you_asked or []),
            assumptions=list(task.assumptions or []),
            question=task.question or "",
            pending_field=task.pending_field or "",
            capabilities=list(task.capabilities or []),
            source_text=task.source_text or "",
            news_unavailable=bool(task.news_unavailable),
            follow_up=follow_up,
        )
