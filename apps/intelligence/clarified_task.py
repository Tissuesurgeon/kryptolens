from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Mode = Literal["ask", "work"]
TaskStatus = Literal["needs_input", "ready"]
TaskType = Literal[
    "one_shot_research",
    "persistent_monitor",
    "scheduled_brief",
    "watch_plus_investigate",
    "news_brief",
]


class TaskScope(BaseModel):
    assets: list[str] = Field(default_factory=list)
    universe: str = ""
    window: str = ""
    listing_limit: int | None = None


class TaskTrigger(BaseModel):
    conditions: list[dict] = Field(default_factory=list)
    logic: str = "AND"


class ClarifiedTask(BaseModel):
    status: TaskStatus = "ready"
    mode: Mode = "ask"
    task_type: TaskType = "one_shot_research"
    objective: str = ""
    scope: TaskScope = Field(default_factory=TaskScope)
    trigger: TaskTrigger = Field(default_factory=TaskTrigger)
    action: str = "report"
    requested_output: str = "natural_language_report"
    you_asked: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    question: str = ""
    pending_field: str = ""
    capabilities: list[str] = Field(default_factory=list)
    source_text: str = ""
    news_unavailable: bool = False

    def is_persistent(self) -> bool:
        return self.status == "ready" and self.mode == "work"


class TurnResult(BaseModel):
    status: TaskStatus
    question: str = ""
    task: ClarifiedTask | None = None
