"""Relate CoinMarketCap headlines to live quotes. LLM phrases facts; it does not invent prices."""

from __future__ import annotations

import re

from apps.intelligence.compiler import _extract_json
from apps.intelligence.llm import HeuristicProvider, get_provider
from apps.intelligence.observations import MarketObservation
from apps.intelligence.present import _format_usd, _spoken_row

MAX_HEADLINES = 8
MAX_QUOTE_SYMBOLS = 8

RELATE_PROMPT = """Relate CoinMarketCap News/Headlines to live CoinMarketCap quotes.
Use ONLY the facts below. Do not invent headlines, sources, prices, or 24h changes.
Do not claim a headline caused a price move.
If a headline tags an asset, mention that asset's live price and 24h change when a quote exists.
If a headline has no matching quote, say so.
Return ONLY JSON: {"analysis": "2-4 sentences"}

Facts:
"""


def symbols_from_items(items: list[dict]) -> list[str]:
    seen: list[str] = []
    for item in items:
        for asset in item.get("assets") or []:
            symbol = str(asset.get("symbol") or "").strip().upper()
            if symbol and symbol not in seen:
                seen.append(symbol)
            if len(seen) >= MAX_QUOTE_SYMBOLS:
                return seen
    return seen


def attach_quotes(items: list[dict], observations: list[MarketObservation]) -> list[dict]:
    by_symbol = {item.symbol.upper(): item for item in observations if item.symbol}
    attached = []
    for item in items[:MAX_HEADLINES]:
        quotes = []
        for asset in item.get("assets") or []:
            symbol = str(asset.get("symbol") or "").strip().upper()
            obs = by_symbol.get(symbol)
            if not obs:
                continue
            quotes.append(
                {
                    "symbol": obs.symbol,
                    "name": obs.name,
                    "price": obs.price,
                    "price_change_24h": obs.price_change_24h,
                }
            )
        row = dict(item)
        row["quotes"] = quotes
        attached.append(row)
    return attached


def analyze_news(items: list[dict], observations: list[MarketObservation], provider=None) -> str:
    facts = _facts(items, observations)
    provider = provider or get_provider()
    if provider is not None and not isinstance(provider, HeuristicProvider):
        try:
            raw = provider.generate(RELATE_PROMPT + str(facts), kind="news")
            data = _extract_json(raw)
            text = str(data.get("analysis") or "").strip()
            if text and _bound_to_facts(text, items, observations):
                return text
        except Exception:
            pass
    return heuristic_analysis(items, observations)


def heuristic_analysis(items: list[dict], observations: list[MarketObservation]) -> str:
    if not items:
        return "CoinMarketCap returned no News/Headlines for this request."
    parts = []
    used = set()
    for item in items[:4]:
        quotes = item.get("quotes") or []
        if quotes:
            quote_text = " ".join(_spoken_row(row) for row in quotes)
            used.update(str(row.get("symbol") or "").upper() for row in quotes)
        else:
            quote_text = "No matching live quote for the tagged assets."
        title = item.get("title") or "Untitled"
        source = item.get("source_name") or "CoinMarketCap"
        parts.append(f"{quote_text} Headline: {title} ({source}).")
    leftover = [obs for obs in observations if obs.symbol.upper() not in used][:2]
    if leftover and not any((item.get("quotes") or []) for item in items[:4]):
        parts.append("Live quotes: " + " ".join(_spoken_row(_obs_row(obs)) for obs in leftover))
    return " ".join(parts)


def build_news_payload(items: list[dict], observations: list[MarketObservation], analysis: str) -> dict:
    attached = attach_quotes(items, observations)
    return {
        "items": attached,
        "rows": [
            {
                "symbol": item.symbol,
                "name": item.name,
                "price": item.price,
                "price_change_24h": item.price_change_24h,
            }
            for item in observations
        ],
        "analysis": analysis,
        "assets": len(observations),
        "headlines": len(attached),
    }


def _obs_row(obs: MarketObservation) -> dict:
    return {
        "symbol": obs.symbol,
        "name": obs.name,
        "price": obs.price,
        "price_change_24h": obs.price_change_24h,
    }


def _facts(items: list[dict], observations: list[MarketObservation]) -> dict:
    return {
        "headlines": [
            {
                "title": item.get("title"),
                "subtitle": item.get("subtitle"),
                "source_name": item.get("source_name"),
                "assets": [asset.get("symbol") for asset in (item.get("assets") or [])],
            }
            for item in items[:MAX_HEADLINES]
        ],
        "quotes": [
            {
                "symbol": item.symbol,
                "name": item.name,
                "price": item.price,
                "price_change_24h": item.price_change_24h,
            }
            for item in observations
        ],
    }


def _bound_to_facts(text: str, items: list[dict], observations: list[MarketObservation]) -> bool:
    lowered = text.lower()
    forbidden = ("hack", "insider", "i think", "probably caused")
    if any(word in lowered for word in forbidden):
        return False
    titles = [str(item.get("title") or "").strip() for item in items if item.get("title")]
    if titles and not any(title.lower() in lowered for title in titles):
        return False
    invented = re.findall(r"\$[\d,]+(?:\.\d+)?", text)
    allowed = {_format_usd(item.price) for item in observations if item.price is not None}
    for raw in invented:
        if raw not in allowed and not any(raw.replace(",", "") in value.replace(",", "") for value in allowed):
            return False
    return True
