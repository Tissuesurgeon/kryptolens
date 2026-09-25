"""Response answers the user's message from verified facts. It does not invent market numbers."""

from __future__ import annotations

import json
import re

from apps.intelligence.llm import HeuristicProvider, get_provider
from apps.intelligence.present import spoken_result
from apps.intelligence.understanding import provider_is_llm

RESPONSE_SYSTEM = """Read the user's message and answer that request.
Use only the verified facts, claims, and limitations provided.
Do not invent prices, percents, ranks, or headlines.
Do not answer about a different asset than the one they asked about.
Do not name hidden capabilities (Market, Anomaly, Reaction, Historical, Discovery, Regime).
If historical comparisons are present, include: comparable observations, not a prediction.
If verification is inconclusive or unsupported, say so plainly.
Return plain text only.
"""


def compose_reply(
    result,
    verification: dict | None = None,
    evidence: list | None = None,
    provider=None,
    task=None,
) -> str:
    if result and getattr(result, "kind", "") == "no_result":
        message = spoken_result(result)
        if message:
            return message
        return "No matching result was found based on the available CoinMarketCap data."
    fallback = spoken_result(result) or (result.title if result else "I finished this check.")
    payload = (result.payload_json or {}) if result else {}
    claims = list(payload.get("claims") or [])
    limitations = list(payload.get("limitations") or [])
    historical = "historical" in (payload.get("metrics") or {}) or any(
        "comparable observations" in item.lower() for item in limitations
    )
    question = _question_from_task(task)
    asked = _asked_symbols(task)
    rows = list(payload.get("rows") or [])
    if asked and rows and not _rows_cover(asked, rows):
        names = ", ".join(asked)
        return f"I read that as a request about {names}. CoinMarketCap did not return that asset in this result."
    provider = provider or get_provider()
    if provider_is_llm(provider) and not isinstance(provider, HeuristicProvider) and not _verification_blocks(verification):
        answered = _answer_with_model(
            provider,
            question=question,
            fallback=fallback,
            payload=payload,
            claims=claims,
            limitations=limitations,
            verification=verification,
            evidence=evidence,
            historical=historical,
            asked=asked,
            rows=rows,
        )
        if answered:
            return answered
    if getattr(result, "kind", "") in {"comparison", "ranked_table"}:
        text = fallback
        if historical and "comparable observations, not a prediction" not in text.lower():
            text = text.rstrip(".") + ". These are comparable observations, not a prediction."
        return text
    return _heuristic_reply(fallback, claims, limitations, historical, verification)


def _answer_with_model(
    provider,
    *,
    question: str,
    fallback: str,
    payload: dict,
    claims: list,
    limitations: list,
    verification: dict | None,
    evidence: list | None,
    historical: bool,
    asked: list[str],
    rows: list,
) -> str:
    try:
        prompt = RESPONSE_SYSTEM + "\n\nUser message:\n" + (question or "Answer from the verified facts.")
        prompt += "\n\nVerified facts:\n" + fallback
        prompt += "\n\nPayload:\n" + json.dumps(payload, default=str)[:6000]
        prompt += f"\nclaims={claims}\nlimitations={limitations}\n"
        prompt += f"verification={(verification or {}).get('status')}\n"
        if evidence:
            prompt += "evidence=" + ", ".join(getattr(item, "claim", "") for item in evidence[:8]) + "\n"
        text = provider.generate(prompt, kind="response").strip()
    except Exception:
        return ""
    if not text or not _uses_only_known_numbers(text, payload, fallback):
        return ""
    if asked and not _mentions_request(text, asked, rows):
        return ""
    if historical and "comparable observations, not a prediction" not in text.lower():
        text = text.rstrip(".") + ". These are comparable observations, not a prediction."
    return text[:2000]


def _question_from_task(task) -> str:
    if not task:
        return ""
    if isinstance(task, dict):
        asked = list(task.get("you_asked") or [])
        return (asked[-1] if asked else "") or task.get("source_text") or task.get("objective") or ""
    asked = list(getattr(task, "you_asked", None) or [])
    return (asked[-1] if asked else "") or getattr(task, "source_text", "") or getattr(task, "objective", "") or ""


def _asked_symbols(task) -> list[str]:
    if not task:
        return []
    if isinstance(task, dict):
        scope = task.get("scope") or {}
        assets = scope.get("assets") if isinstance(scope, dict) else []
    else:
        scope = getattr(task, "scope", None)
        assets = getattr(scope, "assets", None) or []
    return [str(item).upper() for item in assets or [] if item]


def _rows_cover(asked: list[str], rows: list) -> bool:
    present = {str(row.get("symbol") or "").upper() for row in rows if isinstance(row, dict)}
    return bool(present & set(asked))


def _mentions_request(text: str, asked: list[str], rows: list) -> bool:
    lowered = text.lower()
    names = list(asked)
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol") or "").upper() in asked:
            if row.get("name"):
                names.append(str(row["name"]))
    return any(name.lower() in lowered for name in names if name)


def _uses_only_known_numbers(text: str, payload: dict, fallback: str) -> bool:
    allowed = _numeric_tokens(json.dumps(payload, default=str) + "\n" + fallback)
    for number in _numeric_tokens(text):
        if number in {24, 100}:
            continue
        if any(abs(number - item) < 0.02 for item in allowed):
            continue
        return False
    return True


def _numeric_tokens(text: str) -> list[float]:
    return [float(item) for item in re.findall(r"\d+(?:\.\d+)?", text.replace(",", ""))]


def _verification_blocks(verification: dict | None) -> bool:
    return (verification or {}).get("status") in {"unsupported", "inconclusive", "needs_more_evidence"}


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
        return "I do not have enough CoinMarketCap evidence to answer that. Verification is inconclusive."
    if status == "unsupported":
        return "I could not support this from the CoinMarketCap evidence, so I will not treat it as a finding."
    if historical and not any("comparable observations" in item.lower() for item in bits):
        bits.append("These are comparable observations, not a prediction.")
    for note in limitations[:1]:
        if note and note not in " ".join(bits):
            bits.append(note)
    return " ".join(bits).strip()
