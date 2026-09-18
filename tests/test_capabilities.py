from apps.intelligence.calculations import (
    historical_comparison,
    market_breadth,
    rank_change,
    relative_performance,
    volume_ratio,
)
from apps.intelligence.capabilities import run_capabilities
from apps.intelligence.clarified_task import ClarifiedTask, TaskScope
from apps.intelligence.observations import MarketObservation


def _obs(symbol, change, volume_change=10, rank=1, previous=None):
    return MarketObservation(
        asset_id=1 if symbol == "BTC" else 2,
        symbol=symbol,
        name=symbol,
        price=100,
        price_change_24h=change,
        volume_24h=1_000_000,
        volume_change_24h=volume_change,
        market_cap_rank=rank,
        previous_market_cap_rank=previous,
    )


def test_market_breadth_and_relative():
    rows = [_obs("BTC", -2.0), _obs("ETH", -4.0), _obs("SOL", 1.0)]
    breadth = market_breadth(rows)
    assert breadth["declining"] == 2
    assert relative_performance(rows[1], rows[0]) == -2.0
    assert volume_ratio(rows[0]) == 10
    assert rank_change(_obs("ETH", -1, rank=3, previous=5)) == 2
    compared = historical_comparison(110, 100)
    assert compared["percent_change"] == 10


def test_six_capabilities_run():
    task = ClarifiedTask(
        mode="work",
        task_type="watch_plus_investigate",
        capabilities=["market", "anomaly", "reaction", "historical", "discovery", "regime"],
        scope=TaskScope(assets=["BTC"], universe="top_100"),
    )
    observations = [_obs("BTC", -3.0, volume_change=90), _obs("ETH", -6.0, volume_change=100, rank=4, previous=10)]
    results = run_capabilities(task.capabilities, observations, None, task, extras={})
    names = {item.name for item in results}
    assert names == {"market", "anomaly", "reaction", "historical", "discovery", "regime"}
    historical = next(item for item in results if item.name == "historical")
    assert any("not a prediction" in note.lower() for note in historical.limitations)
