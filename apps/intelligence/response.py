"""Response answers the user's message from verified facts. It does not invent market numbers."""

from __future__ import annotations

import json
import re

from apps.intelligence.compiler import _extract_json
from apps.intelligence.llm import HeuristicProvider, get_provider
from apps.intelligence.present import spoken_result
from apps.intelligence.understanding import provider_is_llm

RESPONSE_SYSTEM = """You are a crypto market analyst answering the user's message.
Write a briefing, not a one-line quote and not a system status.

Use only numbers, names, and labels that appear in the verified facts or payload.
Do not invent prices, percents, ranks, volume, headlines, catalysts, or support levels.
Do not round a figure into a different number. Quote the figures as given.
Do not answer about a different asset than the one they asked about.
Do not recommend buying, selling, or shorting.
Do not name hidden capabilities (Market, Anomaly, Reaction, Historical, Discovery, Regime).
When verification is supported or absent, do not mention verification, evidence, or "verified facts".
When verification is inconclusive or unsupported, say the evidence does not support a finding and do not state the price as a finding.
If historical comparisons are present, include: comparable observations, not a prediction.

Shape:
- If the payload has a window and a row has window_change, open with that change over window_label. Name the start and end prices, then the latest price. Do not open with the 24-hour change. The 24-hour change is context after the window.
- If the payload has a window and window_change is missing, say that history was not returned and that the 24-hour quotes are not that comparison. Do not present them as the answer.
- Otherwise open with the direct answer in the asset's name: the live level and the 24-hour change when those are present.
- Then two or three short paragraphs on what those figures show. Use market_cap_label, volume_label, volume_change_label, and rank when they are present. Do not print market_cap or volume_24h. If a field is missing, leave it out.
- A "today" question is the trailing 24-hour CoinMarketCap snapshot, not a forecast and not a full session replay.
- For a ranking, name the leaders from the rows and what the ordering is.
- For a comparison, take each named asset in turn, then the difference that the figures support.

News, from relevant_headlines only:
- Answer the user's question first from the CoinMarketCap quote.
- If relevant_headlines has one or more items, add one short paragraph. Quote those titles, say they are CoinMarketCap headlines, and use each reason. Do not claim a headline caused the price move.
- If headlines_fetched is true, headlines_judged is true, and relevant_headlines is empty, answer the market question and say the latest CoinMarketCap headlines were not relevant to the request. Do not recite unrelated titles.
- If headlines_fetched is false or headlines_judged is false, omit news. Do not invent a story.
Return plain text only. No headings, no bullets.
"""

RELEVANCE_SYSTEM = """You judge whether CoinMarketCap headlines bear on the user's question.
You receive the user's message and headline titles only.
Return ONLY JSON: {"relevant": [{"title": "<exact title>", "reason": "<one line>"}]}
Include a title only when it bears on what they asked. Leave the rest out.
Do not invent titles. Copy titles exactly. If none bear on the question, return {"relevant": []}.
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
    if provider_is_llm(provider) and not isinstance(provider, HeuristicProvider):
        _judge_headlines(provider, question, payload, result)
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
        if _verification_blocks(verification):
            return _heuristic_reply(fallback, claims, limitations, historical, verification)
        return "I have the CoinMarketCap result, but I won't state a number that isn't in it."
    if getattr(result, "kind", "") in {"comparison", "ranked_table"}:
        text = _with_requested_market_cap(fallback, question, payload)
        if historical and "comparable observations, not a prediction" not in text.lower():
            text = text.rstrip(".") + ". These are comparable observations, not a prediction."
        return text
    return _heuristic_reply(fallback, claims, limitations, historical, verification)


def _briefing_row(row):
    if not isinstance(row, dict):
        return row
    cleaned = dict(row)
    if cleaned.get("market_cap_label"):
        cleaned.pop("market_cap", None)
    if cleaned.get("volume_label"):
        cleaned.pop("volume_24h", None)
    if cleaned.get("volume_change_label"):
        cleaned.pop("volume_change_24h", None)
    return cleaned


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
        briefing = {key: value for key, value in payload.items() if key != "headlines"}
        briefing["rows"] = [_briefing_row(row) for row in list(briefing.get("rows") or [])]
        prompt += "\n\nPayload:\n" + json.dumps(briefing, default=str)[:6000]
        prompt += f"\nclaims={claims}\nlimitations={limitations}\n"
        prompt += f"verification={(verification or {}).get('status')}\n"
        if evidence:
            prompt += "evidence=" + ", ".join(getattr(item, "claim", "") for item in evidence[:8]) + "\n"
        text = _accepted_reply(
            provider.generate(prompt, kind="response").strip(),
            payload=payload,
            fallback=fallback,
            verification=verification,
            asked=asked,
            rows=rows,
            historical=historical,
        )
        if text:
            return text
        retry = (
            prompt
            + "\n\nThe previous answer was rejected. Rewrite it from the verified facts only. "
            + "Do not add a price, percent, rank, or asset that is not in those facts."
        )
        text = _accepted_reply(
            provider.generate(retry, kind="response").strip(),
            payload=payload,
            fallback=fallback,
            verification=verification,
            asked=asked,
            rows=rows,
            historical=historical,
        )
        return text or ""
    except Exception:
        return ""


def _accepted_reply(
    text: str,
    *,
    payload: dict,
    fallback: str,
    verification: dict | None,
    asked: list[str],
    rows: list,
    historical: bool,
) -> str:
    if not text or not _uses_only_known_numbers(text, payload, fallback):
        return ""
    if _verification_blocks(verification) and any(number not in {24, 100} for number in _numeric_tokens(text)):
        return ""
    if asked and not _mentions_request(text, asked, rows):
        return ""
    if historical and "comparable observations, not a prediction" not in text.lower():
        text = text.rstrip(".") + ". These are comparable observations, not a prediction."
    return text[:4000]


def _with_requested_market_cap(text: str, question: str, payload: dict) -> str:
    if "market cap" not in (question or "").lower():
        return text
    bits = []
    for row in payload.get("rows") or []:
        if not isinstance(row, dict) or row.get("market_cap") in (None, ""):
            continue
        bits.append(f"{row.get('symbol') or row.get('name')} market cap is {_compact_usd(row.get('market_cap'))}")
    if not bits:
        return text
    return text.rstrip(".") + ". " + ". ".join(bits) + "."


def _compact_usd(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "unavailable"
    absolute = abs(number)
    if absolute >= 1_000_000_000_000:
        return f"${number / 1_000_000_000_000:.2f}T"
    if absolute >= 1_000_000_000:
        return f"${number / 1_000_000_000:.2f}B"
    if absolute >= 1_000_000:
        return f"${number / 1_000_000:.2f}M"
    return f"${number:,.0f}"


def _judge_headlines(provider, question: str, payload: dict, result) -> None:
    headlines = payload.get("headlines")
    if not isinstance(headlines, list) or not headlines:
        payload["headlines_fetched"] = False
        payload["headlines_judged"] = True
        payload["relevant_headlines"] = []
        _store_relevance(result, payload)
        return
    payload["headlines_fetched"] = True
    judged, relevant = _select_relevant(provider, question, headlines)
    payload["headlines_judged"] = judged
    payload["relevant_headlines"] = relevant
    _store_relevance(result, payload)


def _select_relevant(provider, question: str, headlines: list[dict]) -> tuple[bool, list[dict]]:
    titles = [item.get("title") for item in headlines if item.get("title")]
    prompt = RELEVANCE_SYSTEM + "\n\nUser message:\n" + (question or "") + "\n\nTitles:\n" + json.dumps(titles)
    try:
        data = _extract_json(provider.generate(prompt, kind="relevance"))
    except Exception:
        return False, []
    by_title = {item.get("title"): item for item in headlines if item.get("title")}
    kept: list[dict] = []
    seen: set[str] = set()
    for row in data.get("relevant") or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "")
        match = by_title.get(title)
        if not match or title in seen:
            continue
        seen.add(title)
        kept.append({**match, "reason": str(row.get("reason") or "").strip()})
    return True, kept


def _store_relevance(result, payload: dict) -> None:
    if result is None:
        return
    current = dict(getattr(result, "payload_json", None) or {})
    current["headlines_fetched"] = payload.get("headlines_fetched")
    current["headlines_judged"] = payload.get("headlines_judged")
    current["relevant_headlines"] = payload.get("relevant_headlines") or []
    result.payload_json = current
    if getattr(result, "pk", None) and callable(getattr(result, "save", None)):
        result.save(update_fields=["payload_json"])


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
    scaled = []
    for item in allowed:
        for divisor in (1_000_000, 1_000_000_000, 1_000_000_000_000):
            if abs(item) >= divisor:
                scaled.append(item / divisor)
    allowed = allowed + scaled
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
