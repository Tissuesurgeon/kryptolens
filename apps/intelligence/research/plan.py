"""The short ordered investigation. It names capabilities; it does not call CMC."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResearchStep(BaseModel):
    label: str
    capability: str = ""


class ResearchPlan(BaseModel):
    objective: str = ""
    steps: list[ResearchStep] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)

    @classmethod
    def from_capabilities(cls, objective: str, capabilities: list[str], task=None) -> ResearchPlan:
        labels = {
            "market": "Load live CoinMarketCap quotes",
            "historical": "Compare with earlier observations",
            "anomaly": "Check the move against the stated criteria",
            "reaction": "Rank how the universe moved with the trigger",
            "discovery": "Scan listings for the requested rank",
            "regime": "Read market-wide context",
        }
        steps = [ResearchStep(label=labels.get(name, name), capability=name) for name in capabilities]
        if task is not None and getattr(task, "assets", None):
            names = ", ".join(task.assets[:4])
            if names and steps:
                steps[0] = ResearchStep(label=f"Load live quotes for {names}", capability=steps[0].capability)
        return cls(objective=objective, steps=steps, capabilities=list(capabilities))
