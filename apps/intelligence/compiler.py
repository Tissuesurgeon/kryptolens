from __future__ import annotations

import json
import re

from .llm import LLMProvider, get_provider
from .policy import IntelligencePolicy

INTENT_SYSTEM = """You compile human crypto-monitoring intent into a JSON IntelligencePolicy.
Return ONLY valid JSON. No markdown. No tools. No file edits.

Schema:
{
  "version": 1,
  "name": "short name",
  "universe": {"type": "listings"|"symbols", "limit": 100, "exclude_stablecoins": true, "symbols": []},
  "metrics": {
    "observed": ["price_change_24h", "volume_change_24h", "market_cap_rank"],
    "context": ["fear_greed"],
    "derived": ["rank_improved"]
  },
  "asset_conditions": [{"metric": "...", "operator": ">"|">="|"<"|"<="|"==", "value": number|bool}],
  "logic": "AND",
  "market_context": [{"metric": "fear_greed", "operator": ">=", "value": 70}],
  "min_notify_severity": "medium"|"high"|"low",
  "actions": ["store_event", "notify_telegram"],
  "assumptions": ["..."],
  "summary": "one sentence",
  "interesting_event": "what counts as interesting"
}

Rules:
- Fear & Greed is market context, never an asset condition.
- rank_improved is derived, not a CMC field.
- Do not invent metrics outside the schema.
- If the user names a listing size (top 20, top 50, top 100), set universe.limit to that number. Never rewrite an explicit size to 100.
- Prefer listings top 100 only when the user says "biggest", "top", or "altcoins" without a number.
- For a single named coin use universe.type=symbols.
- If the user asks how a coin is doing now or today, do not invent a percent threshold or a watch condition. That is a live snapshot, not a standing trigger.
- If the user is making an existing policy stricter, raise numeric thresholds.
"""


WATCH_MARKERS = (
    "when ",
    "whenever",
    "every time",
    "alert me",
    "notify me",
    "watch until",
    "every morning",
)
STATUS_ASKS = (
    "how is",
    "how's",
    "how are",
    "doing on the market",
    "doing today",
    "doing right now",
    "what's the price",
    "what is the price",
    "price of",
    "how much is",
)


GAINERS_ASKS = (
    "highest gain",
    "highest gains",
    "top gainer",
    "top gainers",
    "biggest gain",
    "biggest gains",
    "best performing",
    "top performing",
    "what is pumping",
    "biggest winner",
    "gainers",
    "most gained",
    "24h gain",
    "24hr gain",
    "24 hour gain",
)
LOSERS_ASKS = (
    "top loser",
    "biggest loser",
    "worst performing",
    "highest loss",
    "biggest declin",
    "largest declin",
    "biggest drop",
    "losers",
)


def is_now_status(text: str) -> bool:
    """True for a live snapshot question, not a standing watch."""
    lowered = text.lower()
    if any(marker in lowered for marker in WATCH_MARKERS):
        return False
    if is_gainers_ask(text) or is_losers_ask(text):
        return False
    if any(ask in lowered for ask in STATUS_ASKS):
        return True
    named = bool(re.search(r"\b(btc|bitcoin|eth|ethereum|sol|solana)\b", lowered))
    snapshot = any(token in lowered for token in (" today", " right now", " currently"))
    return named and snapshot


def is_gainers_ask(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in WATCH_MARKERS):
        return False
    return any(stem in lowered for stem in GAINERS_ASKS)


def is_losers_ask(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in WATCH_MARKERS):
        return False
    if is_gainers_ask(text):
        return False
    return any(stem in lowered for stem in LOSERS_ASKS)


def extract_listing_limit(text: str, default: int = 100) -> int:
    """Honor an explicit 'top N'. Last match wins on edits like 'instead of top 100, use top 20'."""
    matches = re.findall(r"\btop\s+(\d+)\b", text, flags=re.I)
    if not matches:
        return default
    return max(1, min(int(matches[-1]), 500))


def compile_intent(
    text: str,
    provider: LLMProvider | None = None,
    current_policy: IntelligencePolicy | None = None,
) -> IntelligencePolicy:
    provider = provider or get_provider()
    prompt = INTENT_SYSTEM + "\n\nUser intent:\n" + text.strip()
    if current_policy:
        prompt += "\n\nCurrent policy JSON:\n" + current_policy.model_dump_json()
        prompt += "\nUpdate the policy to match the new instruction. Keep universe unless the user changes it."
    raw = provider.generate(prompt, kind="intent")
    data = _extract_json(raw)
    return IntelligencePolicy.model_validate(data)


def compile_intent_safe(
    text: str,
    provider: LLMProvider | None = None,
    current_policy: IntelligencePolicy | None = None,
) -> IntelligencePolicy:
    return compile_intent_report(text, provider=provider, current_policy=current_policy)["policy"]


def compile_intent_report(
    text: str,
    provider: LLMProvider | None = None,
    current_policy: IntelligencePolicy | None = None,
) -> dict:
    """Compile intent and attach asked-vs-assumed interpretation metadata.

    Confidence is interpretation confidence, never a market prediction.
    """
    used_heuristic = False
    try:
        policy = compile_intent(text, provider=provider, current_policy=current_policy)
        confidence = 0.94
    except Exception:
        used_heuristic = True
        policy = HeuristicCompiler().compile(text, current_policy=current_policy)
        confidence = 0.86
    return {
        "policy": policy,
        "you_asked": infer_you_asked(text, policy),
        "assumptions": list(policy.assumptions),
        "clarification": None,
        "confidence": confidence,
        "used_heuristic": used_heuristic,
    }


def infer_you_asked(text: str, policy: IntelligencePolicy) -> list[str]:
    asked: list[str] = []
    lowered = text.lower()
    if policy.universe.type == "listings":
        asked.append(f"top {policy.universe.limit} altcoins" if "alt" in lowered else f"top {policy.universe.limit} assets")
    elif policy.universe.symbols:
        asked.append(", ".join(policy.universe.symbols))
    if any(word in lowered for word in ("price", "momentum", "unusual", "volatil", "rise", "move")):
        asked.append("unusual price activity")
    if "volume" in lowered or "momentum" in lowered or "unusual" in lowered:
        asked.append("unusual volume activity")
    if "rank" in lowered:
        asked.append("improving market-cap rank")
    if any(word in lowered for word in ("greed", "fear", "sentiment")):
        asked.append("Fear & Greed as market context")
    if not asked:
        asked.append(text.strip()[:160] or policy.name)
    # Preserve order, drop duplicates
    seen: set[str] = set()
    unique = []
    for item in asked:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


class HeuristicCompiler:
    """Deterministic fallback when Composer is unavailable."""

    def compile(self, text: str, current_policy: IntelligencePolicy | None = None) -> IntelligencePolicy:
        lowered = text.lower()
        if current_policy and _is_stricter(lowered):
            return _make_stricter(current_policy, text)

        symbols = _extract_symbols(text)
        numbers = [float(item) for item in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)]
        snapshot = is_now_status(text)
        price_value = numbers[0] if numbers else (None if snapshot else 5.0)
        volume_value = numbers[1] if len(numbers) > 1 else 80.0

        wants_rank = any(word in lowered for word in ("rank", "momentum", "unusual", "altcoin"))
        wants_volume = "volume" in lowered or "momentum" in lowered or "unusual" in lowered
        wants_btc = bool(symbols) and symbols[0] == "BTC" and "watch" in lowered and "top" not in lowered
        fear = any(word in lowered for word in ("greed", "fear", "sentiment"))

        if wants_btc or (symbols and "top" not in lowered and "alt" not in lowered and len(symbols) <= 3):
            universe = {
                "type": "symbols",
                "limit": 100,
                "exclude_stablecoins": True,
                "symbols": symbols or ["BTC"],
            }
            name = f"{(symbols[0] if symbols else 'BTC')} Volatility"
            assumptions = [f"Interpreted named asset as {', '.join(universe['symbols'])}."]
        else:
            limit = extract_listing_limit(text)
            universe = {
                "type": "listings",
                "limit": limit,
                "exclude_stablecoins": True,
                "symbols": [],
            }
            name = f"Top-{limit} Momentum"
            assumptions = ['"Biggest" / top interpreted as highest market-cap assets.', "Stablecoins excluded."]

        observed = ["price_change_24h"]
        derived = []
        context = []
        conditions = []
        if price_value is not None:
            conditions.append({"metric": "price_change_24h", "operator": ">", "value": price_value})
        if wants_volume:
            observed.append("volume_change_24h")
            conditions.append({"metric": "volume_change_24h", "operator": ">", "value": volume_value})
        if wants_rank:
            observed.append("market_cap_rank")
            derived.append("rank_improved")
            conditions.append({"metric": "rank_improved", "operator": "==", "value": True})
        market_context = []
        if fear or wants_rank or "momentum" in lowered:
            context.append("fear_greed")
            market_context.append({"metric": "fear_greed", "operator": ">=", "value": 70})
            assumptions.append("Fear & Greed is market context, not an asset attribute.")

        if snapshot:
            name = f"{(symbols[0] if symbols else 'BTC')} now"
        if "btc" in lowered and "volatil" in lowered:
            name = "BTC Volatility Watcher"
        if "volume" in lowered and "price" not in lowered and not wants_rank:
            name = "Unusual Volume"

        interesting = "Live snapshot" if snapshot else " + ".join(
            part
            for part, flag in (
                ("Strong price movement", True),
                ("unusual volume", wants_volume),
                ("improving rank", wants_rank),
            )
            if flag
        )

        return IntelligencePolicy.model_validate(
            {
                "version": 1,
                "name": name,
                "universe": universe,
                "metrics": {"observed": observed, "context": context, "derived": derived},
                "asset_conditions": conditions,
                "logic": "AND",
                "market_context": market_context,
                "min_notify_severity": "medium",
                "actions": ["store_event", "notify_telegram"],
                "assumptions": assumptions,
                "summary": text.strip(),
                "interesting_event": interesting or "Configured threshold crossed",
            }
        )


def _is_stricter(text: str) -> bool:
    return any(word in text for word in ("stricter", "only show", "raise", "higher", "ignore", "above"))


def _make_stricter(policy: IntelligencePolicy, text: str) -> IntelligencePolicy:
    data = policy.model_dump()
    percents = [float(item) for item in re.findall(r"(\d+(?:\.\d+)?)\s*%", text)]
    price_override = percents[0] if percents else None
    volume_override = percents[1] if len(percents) > 1 else None
    for condition in data["asset_conditions"]:
        if condition["metric"] == "price_change_24h":
            condition["value"] = price_override if price_override is not None else float(condition["value"]) * 1.5
        if condition["metric"] == "volume_change_24h":
            condition["value"] = volume_override if volume_override is not None else float(condition["value"]) * 2
    data["assumptions"] = list(policy.assumptions) + ["Updated from an existing policy to be stricter."]
    data["summary"] = text.strip()
    return IntelligencePolicy.model_validate(data)


def _extract_symbols(text: str) -> list[str]:
    known = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "AVAX", "LINK", "DOT", "UNI"]
    found = []
    for symbol in known:
        if re.search(rf"\b{symbol}\b", text, re.I):
            found.append(symbol)
    aliases = {"bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL"}
    for word, symbol in aliases.items():
        if word in text.lower() and symbol not in found:
            found.append(symbol)
    return found


def _extract_json(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("LLM did not return JSON")
    return json.loads(text[start : end + 1])
