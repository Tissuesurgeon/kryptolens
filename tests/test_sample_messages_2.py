"""A second set of user messages, different from the first sample list."""

from apps.intelligence.agent import ChiefAgent
from apps.intelligence.conversation_agent import ConversationAgent
from apps.intelligence.research.context import ResearchContext, resolve_follow_up
from apps.intelligence.research.task import ResearchTask
from apps.intelligence.response import compose_reply
from apps.intelligence.task_compiler import compile_from_task
from apps.lenses.conversation_service import ConversationService


def _ready(text: str):
    turn = ConversationAgent.understand(text)
    assert turn.status == "ready", turn.question
    plan = ChiefAgent().plan_from_task(turn.task)
    report = compile_from_task(turn.task, capability_plan=plan)
    return turn, report


def test_past_days_uses_history_for_one_coin():
    turn, report = _ready("how did BTC perform over the past 14 days")
    assert turn.task.scope.assets == ["BTC"]
    assert turn.task.scope.window == "14d"
    assert any(step.type == "get_quotes_historical" for step in report["workflow"].steps)


def test_this_week_compares_both_coins():
    turn, report = _ready("ETH vs SOL this week")
    assert set(turn.task.scope.assets) == {"ETH", "SOL"}
    assert turn.task.scope.window == "7d"
    assert "historical" in turn.task.capabilities


def test_worst_and_best_rank_the_named_slice():
    losers, losers_report = _ready("worst 10 coins right now")
    assert losers.task.action == "rank_declines"
    assert losers.task.scope.listing_limit == 10
    gainers, _gainers_report = _ready("best performers in the top 30")
    assert gainers.task.action == "rank_gains"
    assert gainers.task.scope.listing_limit == 30
    dumping, _dumping_report = _ready("anything dumping hard")
    assert dumping.task.action == "rank_declines"
    assert losers_report["workflow"].steps


def test_a_climb_is_an_upward_watch():
    turn, report = _ready("ping me when DOT climbs past 6%")
    condition = turn.task.trigger.conditions[0]
    assert condition["asset"] == "DOT"
    assert condition["operator"] == ">="
    assert condition["value"] == 6
    assert report["workflow"].trigger.value == 6


def test_a_crash_is_a_downward_watch():
    turn, _report = _ready("notify me if bitcoin crashes 8%")
    condition = turn.task.trigger.conditions[0]
    assert condition["asset"] == "BTC"
    assert condition["value"] == -8
    assert condition["operator"] == "<="


def test_memes_market_trades_and_thanks_do_not_quote_the_wrong_thing():
    memes = ConversationAgent.understand("what about memes")
    assert memes.status == "needs_input"
    assert memes.task.scope.assets == []
    market, market_report = _ready("how is the whole market")
    assert market.task.scope.assets == []
    assert market.task.action == "market_summary"
    assert any(step.type == "get_fear_and_greed" for step in market_report["workflow"].steps)
    fear, fear_report = _ready("show fear and greed")
    assert fear.task.action == "market_summary"
    assert any(step.type == "get_fear_and_greed" for step in fear_report["workflow"].steps)
    trade = ConversationAgent.understand("can you short ETH")
    assert trade.status == "needs_input"
    assert "do not place trades" in trade.question
    buy = ConversationAgent.understand("buy me some SOL")
    assert buy.status == "needs_input"
    assert "do not place trades" in buy.question
    thanks = ConversationAgent.understand("thanks")
    assert thanks.status == "needs_input"
    assert "Okay" in thanks.question


def test_correction_keeps_only_the_coin_they_meant():
    turn, report = _ready("I meant SOL not BTC")
    assert turn.task.scope.assets == ["SOL"]
    assert report["workflow"].steps[0].symbols == ["SOL"]


def test_market_cap_is_spoken_when_asked():
    class Result:
        kind = "comparison"
        title = "LINK"
        payload_json = {"rows": [{"symbol": "LINK", "name": "Chainlink", "price": 15.5, "price_change_24h": 1.1, "market_cap": 9_200_000_000}]}

    text = compose_reply(
        Result(),
        task={"you_asked": ["what's the market cap of LINK"], "scope": {"assets": ["LINK"]}},
    )
    assert "LINK market cap is $9.20B" in text
    assert "15.50" in text


def test_follow_ups_keep_the_current_research():
    context = ResearchContext()
    context.apply_task(
        ResearchTask(
            assets=["ETH", "SOL"],
            window="7d",
            objective="Compare ETH and SOL",
            capabilities=["historical", "market"],
            source_text="ETH vs SOL this week",
            mode="ask",
        )
    )
    window = resolve_follow_up("same coins, last 90 days", context)
    assert window.task.scope.assets == ["ETH", "SOL"]
    assert window.task.scope.window == "90d"
    added = resolve_follow_up("also look at XRP", context)
    assert added.task.scope.assets == ["ETH", "SOL", "XRP"]
    deeper = resolve_follow_up("dig into that comparison", context)
    assert "historical" in deeper.task.capabilities
    weird = resolve_follow_up("was the move on ETH weird", context)
    assert weird.task.scope.assets == ["ETH"]
    assert "anomaly" in weird.task.capabilities


def test_keep_an_eye_on_a_coin_does_not_drop_the_coin():
    turn = ConversationAgent.understand("keep an eye on ETH")
    assert turn.status == "needs_input"
    assert turn.task.scope.assets == ["ETH"]
    assert "ETH" in turn.question
    assert ConversationService.command("please keep watching this") == "watch"
    assert ConversationService.command("keep an eye on eth") is None
