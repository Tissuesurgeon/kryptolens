from apps.intelligence.engine import compare, evaluate_policy, severity_from_score
from apps.intelligence.observations import MarketContext, MarketObservation
from apps.intelligence.planner import plan_query
from apps.intelligence.policy import IntelligencePolicy


def _policy(**overrides):
    data = {
        "name": "Test",
        "universe": {"type": "listings", "limit": 100},
        "metrics": {
            "observed": ["price_change_24h", "volume_change_24h", "market_cap_rank"],
            "context": ["fear_greed"],
            "derived": ["rank_improved"],
        },
        "asset_conditions": [
            {"metric": "price_change_24h", "operator": ">", "value": 5},
            {"metric": "volume_change_24h", "operator": ">", "value": 80},
            {"metric": "rank_improved", "operator": "==", "value": True},
        ],
        "logic": "AND",
        "market_context": [{"metric": "fear_greed", "operator": ">=", "value": 70}],
        "min_notify_severity": "high",
        "actions": ["store_event", "notify_telegram"],
    }
    data.update(overrides)
    return IntelligencePolicy.model_validate(data)


def test_compare_operators():
    assert compare(8, ">", 5) is True
    assert compare(4, ">", 5) is False
    assert compare(5, ">=", 5) is True


def test_and_logic_all_met():
    obs = MarketObservation(
        asset_id=5426,
        symbol="SOL",
        name="Solana",
        price=180,
        price_change_24h=12.4,
        volume_24h=6e9,
        volume_change_24h=210,
        market_cap=8e10,
        market_cap_rank=5,
        previous_market_cap_rank=9,
    )
    context = MarketContext(fear_greed_value=74, fear_greed_label="Greed")
    candidate = evaluate_policy(obs, _policy(), context)
    assert candidate.logic_passed is True
    assert candidate.should_promote is True
    assert candidate.severity == "high"
    assert candidate.score >= 4
    assert "price threshold crossed" in candidate.reasons
    assert "volume threshold crossed" in candidate.reasons
    assert "rank improved" in candidate.reasons
    assert "market context confirmed" in candidate.reasons


def test_and_logic_fails_when_volume_low():
    obs = MarketObservation(
        asset_id=1,
        symbol="BTC",
        price_change_24h=8,
        volume_change_24h=10,
        market_cap_rank=1,
        previous_market_cap_rank=1,
    )
    candidate = evaluate_policy(obs, _policy())
    assert candidate.logic_passed is False
    assert candidate.should_promote is False


def test_rank_improved_skipped_without_snapshot():
    obs = MarketObservation(
        asset_id=1,
        symbol="BTC",
        price_change_24h=8,
        volume_change_24h=90,
        market_cap_rank=1,
    )
    candidate = evaluate_policy(obs, _policy())
    assert "rank_improved" in candidate.skipped_metrics
    assert candidate.logic_passed is True


def test_suppressed_below_notify_threshold():
    policy = _policy(min_notify_severity="high")
    policy.asset_conditions = policy.asset_conditions[:1]
    obs = MarketObservation(asset_id=1, symbol="BTC", price_change_24h=6)
    candidate = evaluate_policy(obs, policy)
    assert candidate.logic_passed is True
    assert candidate.should_promote is True
    assert candidate.should_notify is False
    assert candidate.suppress_reason == "minimum severity threshold not reached"


def test_severity_bands():
    assert severity_from_score(0) == "low"
    assert severity_from_score(1) == "low"
    assert severity_from_score(2) == "medium"
    assert severity_from_score(3) == "medium"
    assert severity_from_score(4) == "high"


def test_missing_price_change_is_not_treated_as_zero():
    obs = MarketObservation(asset_id=1, symbol="SOL", name="Solana", price=10, price_change_24h=None)
    policy = IntelligencePolicy.model_validate(
        {
            "name": "Missing",
            "universe": {"type": "symbols", "symbols": ["SOL"]},
            "metrics": {"observed": ["price_change_24h"], "context": [], "derived": []},
            "asset_conditions": [{"metric": "price_change_24h", "operator": "<=", "value": -2}],
            "logic": "AND",
            "min_notify_severity": "low",
            "actions": ["store_event"],
        }
    )
    candidate = evaluate_policy(obs, policy)
    actuals = [item["actual"] for item in candidate.condition_results]
    assert None in actuals
    assert 0 not in actuals
    assert "price_change_24h" in candidate.skipped_metrics
    assert candidate.logic_passed is False


def test_query_plan_listings():
    plan = plan_query(_policy())
    assert "/v3/cryptocurrency/listings/latest" in plan.endpoints
    assert "/v3/fear-and-greed/latest" in plan.endpoints
    assert plan.requires_previous_snapshot is True
    assert "percent_change_24h" in plan.required_fields
