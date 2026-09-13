from __future__ import annotations

from .observations import Candidate, MarketContext, MarketObservation
from .policy import IntelligencePolicy
from .scoring import SEVERITY_RANK, score_candidate, severity_from_score

__all__ = [
    "compare",
    "evaluate_policy",
    "fallback_explanation",
    "severity_from_score",
    "SEVERITY_RANK",
]


def compare(left, operator: str, right) -> bool:
    if left is None:
        return False
    if operator == ">":
        return left > right
    if operator == ">=":
        return left >= right
    if operator == "<":
        return left < right
    if operator == "<=":
        return left <= right
    if operator == "==":
        return left == right
    raise ValueError(f"unknown operator: {operator}")


def evaluate_policy(
    observation: MarketObservation,
    policy: IntelligencePolicy,
    context: MarketContext | None = None,
) -> Candidate:
    results = []
    skipped = []
    met = 0
    evaluated = 0

    for condition in policy.asset_conditions:
        value = observation.metric_value(condition.metric)
        if value is None:
            skipped.append(condition.metric)
            results.append(
                {
                    "metric": condition.metric,
                    "operator": condition.operator,
                    "expected": condition.value,
                    "actual": None,
                    "met": False,
                    "skipped": True,
                }
            )
            continue
        passed = compare(value, condition.operator, condition.value)
        evaluated += 1
        if passed:
            met += 1
        results.append(
            {
                "metric": condition.metric,
                "operator": condition.operator,
                "expected": condition.value,
                "actual": value,
                "met": passed,
                "skipped": False,
            }
        )

    required = [item for item in results if not item["skipped"]]
    if policy.logic == "OR":
        logic_passed = any(item["met"] for item in required) if required else False
    else:
        logic_passed = bool(required) and all(item["met"] for item in required)

    score, reasons, context_confirmed = score_candidate(
        observation, policy, results, context
    )
    severity = severity_from_score(score)
    notify_ok = SEVERITY_RANK[severity] >= SEVERITY_RANK[policy.min_notify_severity]
    should_promote = logic_passed
    should_notify = (
        should_promote and notify_ok and "notify_telegram" in policy.actions
    )
    suppress_reason = ""
    if logic_passed and not notify_ok:
        suppress_reason = "minimum severity threshold not reached"
    elif not logic_passed and met:
        suppress_reason = "asset conditions not fully met"

    return Candidate(
        observation=observation,
        context=context,
        conditions_evaluated=evaluated,
        conditions_met=met,
        condition_results=results,
        logic_passed=logic_passed,
        score=score,
        reasons=reasons,
        severity=severity,
        context_confirmed=context_confirmed,
        skipped_metrics=skipped,
        should_promote=should_promote,
        should_notify=should_notify,
        suppress_reason=suppress_reason,
    )


def fallback_explanation(candidate: Candidate, policy: IntelligencePolicy) -> str:
    obs = candidate.observation
    bits = [f"{obs.symbol} triggered {policy.name}."]
    if obs.price_change_24h is not None:
        bits.append(f"Price moved {obs.price_change_24h:+.1f}% over 24 hours.")
    if obs.volume_change_24h is not None:
        bits.append(f"Volume changed {obs.volume_change_24h:+.1f}%.")
    if obs.rank_improved:
        bits.append("Market-cap rank improved.")
    if candidate.context_confirmed and candidate.context and candidate.context.fear_greed_label:
        bits.append(
            f"Broader market context: CMC Fear & Greed was "
            f"{candidate.context.fear_greed_value} ({candidate.context.fear_greed_label})."
        )
    if candidate.reasons:
        bits.append("Why this matters: " + ", ".join(candidate.reasons) + ".")
    return " ".join(bits)
