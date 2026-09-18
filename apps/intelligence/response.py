"""Response LLM phrases verified facts. It does not invent market numbers."""

from __future__ import annotations

from apps.intelligence.llm import HeuristicProvider, get_provider
from apps.intelligence.present import spoken_result
from apps.intelligence.understanding import provider_is_llm

RESPONSE_SYSTEM = """You write a 2-4 sentence reply for a KryptoLens user.
Use only the verified facts, claims, and limitations provided.
Do not invent prices, percents, ranks, or headlines.
Do not name hidden capabilities (Market, Anomaly, Reaction, Historical, Discovery, Regime).
If historical comparisons are present, include: comparable observations, not a prediction.
If verification is inconclusive or unsupported, say so plainly.
Return plain text only.
"""


def compose_reply(result, verification: dict | None = None, evidence: list | None = None, provider=None) -> str:
    fallback = spoken_result(result) or (result.title if result else "I finished this check.")
    payload = (result.payload_json or {}) if result else {}
    claims = list(payload.get("claims") or [])
    limitations = list(payload.get("limitations") or [])
    historical = "historical" in (payload.get("metrics") or {}) or any(
        "comparable observations" in item.lower() for item in limitations
    )
    provider = provider or get_provider()
    if not provider_is_llm(provider) or isinstance(provider, HeuristicProvider):
        return _heuristic_reply(fallback, claims, limitations, historical, verification)
    try:
        prompt = RESPONSE_SYSTEM + "\n\nVerified payload:\n"
        prompt += f"kind={getattr(result, 'kind', '')}\n"
        prompt += f"spoken={fallback}\n"
        prompt += f"claims={claims}\n"
        prompt += f"limitations={limitations}\n"
        prompt += f"verification={(verification or {}).get('status')}\n"
        if evidence:
            prompt += "evidence=" + ", ".join(getattr(item, "claim", "") for item in evidence[:8]) + "\n"
        text = provider.generate(prompt, kind="response").strip()
        if text:
            if historical and "comparable observations, not a prediction" not in text.lower():
                text = text.rstrip(".") + ". These are comparable observations, not a prediction."
            return text[:2000]
    except Exception:
        pass
    return _heuristic_reply(fallback, claims, limitations, historical, verification)


def _heuristic_reply(
    fallback: str,
    claims: list[str],
    limitations: list[str],
    historical: bool,
    verification: dict | None,
) -> str:
    bits = [fallback] if fallback else []
    for claim in claims[:2]:
        if claim and claim not in fallback:
            bits.append(claim)
    status = (verification or {}).get("status")
    if status in {"inconclusive", "needs_more_evidence"}:
        bits.append("Verification is inconclusive on this run.")
    elif status == "unsupported":
        bits.append("I could not support this result from the CoinMarketCap evidence.")
    if historical and not any("comparable observations" in item.lower() for item in bits):
        bits.append("These are comparable observations, not a prediction.")
    for note in limitations[:1]:
        if note and note not in " ".join(bits):
            bits.append(note)
    return " ".join(bits).strip()
