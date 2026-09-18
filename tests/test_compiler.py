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


def test_heuristic_honors_top_20():
    policy = HeuristicCompiler().compile(
        "Watch the top 20 altcoins for unusual momentum."
    )
    assert policy.universe.limit == 20
    assert policy.name == "Top-20 Momentum"


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


def test_bitcoin_today_is_a_snapshot_not_a_5_percent_watch():
    from apps.intelligence.compiler import is_now_status
    from apps.intelligence.job_compiler import compile_job_report

    text = "how is bitcoin doing on the market today"
    assert is_now_status(text)
    policy = HeuristicCompiler().compile(text)
    assert policy.universe.symbols == ["BTC"]
    assert policy.asset_conditions == []
    report = compile_job_report(text, provider=HeuristicProvider())
    job = report["job"]
    workflow = report["workflow"]
    assert job.execution_model == "task"
    assert job.is_persistent() is False
    assert job.you_asked == [text]
    assert workflow.trigger is None
    assert [step.type for step in workflow.steps] == ["get_quotes", "present"]
    assert workflow.steps[0].symbols == ["BTC"]
    assert "5.0" not in (job.trigger_summary or "")


def test_eth_snapshot_does_not_keep_btc_from_current_policy():
    from apps.intelligence.job_compiler import _status_now

    policy = HeuristicCompiler().compile("how is bitcoin doing on the market today")
    _, workflow, updated = _status_now("what is ETH doing right now", policy)
    assert workflow.steps[0].symbols == ["ETH"]
    assert updated.universe.symbols == ["ETH"]


def test_highest_gains_compiles_to_listings_rank():
    from apps.intelligence.compiler import is_gainers_ask
    from apps.intelligence.job_compiler import compile_job_report
    from apps.intelligence.llm import HeuristicProvider

    text = "find me the coins with the highest gains within 24hrs"
    assert is_gainers_ask(text)
    report = compile_job_report(text, provider=HeuristicProvider())
    assert report["job"].execution_model == "task"
    assert report["job"].is_persistent() is False
    assert report["workflow"].steps[0].type == "get_universe"
    assert any(step.type == "sort" and step.order == "descending" for step in report["workflow"].steps)
