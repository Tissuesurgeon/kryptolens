from apps.intelligence.engine import fallback_explanation
from apps.intelligence.explain import _bound_to_facts
from apps.intelligence.observations import Candidate, MarketObservation
from apps.intelligence.policy import IntelligencePolicy


def test_explanation_rejects_invented_causes():
    candidate = Candidate(
        observation=MarketObservation(asset_id=1, symbol="BTC", price_change_24h=6),
        reasons=["price threshold crossed"],
    )
    assert _bound_to_facts("BTC pumped because of news and a hack.", candidate) == ""


def test_fallback_stays_on_observed_facts():
    policy = IntelligencePolicy.model_validate(
        {
            "name": "BTC Volatility",
            "universe": {"type": "symbols", "symbols": ["BTC"]},
            "metrics": {"observed": ["price_change_24h"]},
            "asset_conditions": [{"metric": "price_change_24h", "operator": ">", "value": 5}],
        }
    )
    text = fallback_explanation(
        Candidate(observation=MarketObservation(asset_id=1, symbol="BTC", price_change_24h=6.2)),
        policy,
    )
    assert "BTC" in text
    assert "6.2" in text
    assert "hack" not in text.lower()
