from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ExecutionModel = Literal["task", "watch", "scheduled", "watch_plus_workflow"]
RoutineKind = Literal["manual", "interval", "scheduled", "event_triggered"]


class JobDefinition(BaseModel):
    """Product-level assignment for a Lens. Policy and workflow are derived from this."""

    purpose: str
    summary: str = ""
    execution_model: ExecutionModel = "watch"
    mode: Literal["ask", "work"] | None = None
    routine_kind: RoutineKind | None = None
    trigger_summary: str = ""
    workflow_summary: str = ""
    news_unavailable: bool = False
    you_asked: list[str] = Field(default_factory=list)
    steps_explained: list[str] = Field(default_factory=list)

    def is_persistent(self) -> bool:
        if self.mode == "ask":
            return False
        if self.mode == "work":
            return self.routine_kind not in {None, "manual"}
        return self.execution_model in {"watch", "scheduled", "watch_plus_workflow"} and self.routine_kind not in {
            None,
            "manual",
        }
