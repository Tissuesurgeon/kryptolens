from __future__ import annotations

from .observations import MarketContext, MarketObservation
from .policy import IntelligencePolicy, Severity

SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3}


def score_high_min() -> int:
    try:
        from django.conf import settings

        return int(getattr(settings, "SCORE_HIGH_MIN", 4))
    except Exception:
        return 4


def score_medium_min() -> int:
    try:
        from django.conf import settings

        return int(getattr(settings, "SCORE_MEDIUM_MIN", 2))
    except Exception:
        return 2


def strong_move_multiplier() -> float:
    try:
        from django.conf import settings

        return float(getattr(settings, "SCORE_STRONG_MOVE_MULTIPLIER", 2))
    except Exception:
        return 2.0


def severity_from_score(score: int) -> Severity:
    if score >= score_high_min():
        return "high"
    if score >= score_medium_min():
        return "medium"
    return "low"


def score_candidate(
    observation: MarketObservation,
    policy: IntelligencePolicy,
    condition_results: list[dict],
    context: MarketContext | None = None,
) -> tuple[int, list[str], bool]:
    reasons: list[str] = []
    score = 0
    for item in condition_results:
        if item.get("met"):
            score += 1
            reasons.append(_reason_for(item["metric"]))

    multiplier = strong_move_multiplier()
    price_threshold = _threshold(policy, "price_change_24h")
    if (
        price_threshold is not None
        and observation.price_change_24h is not None
        and observation.price_change_24h >= multiplier * abs(price_threshold)
    ):
        score += 1
        reasons.append("strong movement")

    volume_threshold = _threshold(policy, "volume_change_24h")
    if (
        volume_threshold is not None
        and observation.volume_change_24h is not None
        and observation.volume_change_24h >= multiplier * abs(volume_threshold)
    ):
        score += 1
        reasons.append("volume anomaly")

    if observation.rank_improved is True and "rank improved" not in reasons:
        score += 1
        reasons.append("rank improved")

    context_confirmed = False
    if context and policy.market_context:
        from .engine import compare

        context_hits = []
        for condition in policy.market_context:
            actual = context.metric_value(condition.metric)
            if actual is None:
                continue
            context_hits.append(compare(actual, condition.operator, condition.value))
        context_confirmed = bool(context_hits) and all(context_hits)
        if context_confirmed:
            score += 1
            reasons.append("market context confirmed")

    return score, reasons, context_confirmed


def _threshold(policy: IntelligencePolicy, metric: str) -> float | None:
    for condition in policy.asset_conditions:
        if condition.metric == metric:
            try:
                return float(condition.value)
            except (TypeError, ValueError):
                return None
    return None


def _reason_for(metric: str) -> str:
    return {
        "price_change_24h": "price threshold crossed",
        "volume_change_24h": "volume threshold crossed",
        "rank_improved": "rank improved",
        "market_cap_rank": "rank condition met",
        "market_cap": "market-cap condition met",
    }.get(metric, f"{metric} condition met")
