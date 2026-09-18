from __future__ import annotations

from apps.intelligence.capabilities.anomaly import AnomalyCapability
from apps.intelligence.capabilities.base import CapabilityResult
from apps.intelligence.capabilities.discovery import DiscoveryCapability
from apps.intelligence.capabilities.historical import HistoricalCapability
from apps.intelligence.capabilities.market import MarketCapability
from apps.intelligence.capabilities.reaction import ReactionCapability
from apps.intelligence.capabilities.regime import RegimeCapability
from apps.intelligence.clarified_task import ClarifiedTask
from apps.intelligence.observations import MarketContext, MarketObservation

CAPABILITIES = {
    "market": MarketCapability(),
    "anomaly": AnomalyCapability(),
    "reaction": ReactionCapability(),
    "historical": HistoricalCapability(),
    "discovery": DiscoveryCapability(),
    "regime": RegimeCapability(),
}


def select_capabilities(task: ClarifiedTask | None, names: list[str] | None = None) -> list:
    chosen = list(names or (task.capabilities if task else []) or ["market"])
    selected = []
    for name in chosen:
        cap = CAPABILITIES.get(name)
        if cap and (task is None or cap.accepts(task)):
            selected.append(cap)
    if not selected:
        selected.append(CAPABILITIES["market"])
    return selected


def required_tools(task: ClarifiedTask | None, names: list[str] | None = None) -> list[str]:
    tools: list[str] = []
    for cap in select_capabilities(task, names):
        for tool in cap.required_tools(task or ClarifiedTask()):
            if tool not in tools:
                tools.append(tool)
    return tools


def run_capabilities(
    names: list[str],
    observations: list[MarketObservation],
    context: MarketContext | None,
    task: ClarifiedTask | None = None,
    extras: dict | None = None,
) -> list[CapabilityResult]:
    task = task or ClarifiedTask()
    results = []
    for cap in select_capabilities(task, names):
        results.append(cap.analyze(observations, context, task, extras))
    return results


def merge_capability_payload(payload: dict, results: list[CapabilityResult]) -> dict:
    claims: list[str] = list(payload.get("claims") or [])
    limitations: list[str] = list(payload.get("limitations") or [])
    metrics = dict(payload.get("metrics") or {})
    for result in results:
        for claim in result.claims:
            if claim not in claims:
                claims.append(claim)
        for note in result.limitations:
            if note not in limitations:
                limitations.append(note)
        metrics[result.name] = result.metrics
    payload["claims"] = claims
    payload["limitations"] = limitations
    payload["metrics"] = metrics
    return payload
