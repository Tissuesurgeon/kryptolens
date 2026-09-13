from __future__ import annotations

from .compiler import _extract_json
from .engine import fallback_explanation
from .llm import LLMProvider, get_provider
from .observations import Candidate
from .policy import IntelligencePolicy

EXPLAIN_PROMPT = """Write a concise intelligence brief from ONLY these facts.
Do not invent causes, news, or metrics that are not listed.
Return JSON: {"explanation": "2-4 sentences"}

Facts:
"""


def explain_event(
    candidate: Candidate,
    policy: IntelligencePolicy,
    provider: LLMProvider | None = None,
) -> str:
    provider = provider or get_provider()
    facts = {
        "lens": policy.name,
        "asset": candidate.observation.symbol,
        "asset_name": candidate.observation.name,
        "observations": candidate.observation.model_dump(mode="json"),
        "score": candidate.score,
        "reasons": candidate.reasons,
        "severity": candidate.severity,
        "conditions": candidate.condition_results,
        "context": candidate.context.model_dump(mode="json") if candidate.context else None,
    }
    try:
        raw = provider.generate(EXPLAIN_PROMPT + str(facts), kind="explain")
        data = _extract_json(raw)
        text = str(data.get("explanation") or "").strip()
        bounded = _bound_to_facts(text, candidate) if text else ""
        if bounded:
            return bounded
    except Exception:
        pass
    return fallback_explanation(candidate, policy)


def _bound_to_facts(text: str, candidate: Candidate) -> str:
    forbidden = ["because of news", "due to listing", "hack", "partnership", "insider"]
    lowered = text.lower()
    if any(word in lowered for word in forbidden):
        return ""
    return text
