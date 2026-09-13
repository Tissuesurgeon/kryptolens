from apps.intelligence.compiler import HeuristicCompiler, compile_intent_report, compile_intent_safe
from apps.intelligence.llm import HeuristicProvider


def test_btc_price_threshold():
    policy = compile_intent_safe("Alert me when BTC rises more than 5%.")
    assert policy.universe.type == "symbols"
    assert policy.universe.symbols == ["BTC"]
    cond = next(item for item in policy.asset_conditions if item.metric == "price_change_24h")
    assert cond.operator == ">"
    assert cond.value == 5


def test_top100_momentum_heuristic():
    policy = HeuristicCompiler().compile(
        "Watch the biggest altcoins for unusual momentum."
    )
    assert policy.universe.type == "listings"
    assert policy.universe.limit == 100
    assert policy.universe.exclude_stablecoins is True
    metrics = {item.metric for item in policy.asset_conditions}
    assert "price_change_24h" in metrics
    assert "volume_change_24h" in metrics
    assert "rank_improved" in metrics
    assert any(item.metric == "fear_greed" for item in policy.market_context)


def test_stricter_edit():
    original = HeuristicCompiler().compile("Watch BTC for a 5% move")
    updated = HeuristicCompiler().compile(
        "Only show me events above 10% and ignore volume changes below 200%.",
        current_policy=original,
    )
    price = next(item for item in updated.asset_conditions if item.metric == "price_change_24h")
    assert price.value == 10


def test_compile_report_asked_vs_assumed():
    report = compile_intent_report(
        "Watch the top 100 altcoins for unusual price and volume activity.",
        provider=HeuristicProvider(),
    )
    assert "policy" in report
    assert "top 100 altcoins" in report["you_asked"]
    assert "unusual price activity" in report["you_asked"]
    assert "unusual volume activity" in report["you_asked"]
    assert any("stablecoin" in item.lower() for item in report["assumptions"])
    assert report["clarification"] is None
    assert 0 < report["confidence"] <= 1


def test_heuristic_provider_returns_json():
    provider = HeuristicProvider()
    raw = provider.generate("User intent:\nAlert me when ETH rises more than 8%.")
    assert '"ETH"' in raw or '"price_change_24h"' in raw
