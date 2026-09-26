"""Sample user messages and the feedback the analyst should give."""

import pytest

from apps.intelligence.agent import ChiefAgent
from apps.intelligence.conversation_agent import ConversationAgent
from apps.intelligence.task_compiler import compile_from_task
from apps.lenses.conversation_service import ConversationService


def _plan(text: str):
    turn = ConversationAgent.understand(text)
    task = turn.task
    report = None
    if turn.status == "ready" and task is not None:
        plan = ChiefAgent().plan_from_task(task)
        report = compile_from_task(task, capability_plan=plan)
    return turn, report


@pytest.mark.parametrize(
    ("text", "asset"),
    [
        ("how is AR doing ?", "AR"),
        ("how is bitcoin doing on the market today", "BTC"),
        ("what is ETH doing right now", "ETH"),
        ("how's SOL?", "SOL"),
        ("price of DOGE", "DOGE"),
        ("how is PEPE doing", "PEPE"),
        ("what's happening with LINK", "LINK"),
        ("tell me about AVAX", "AVAX"),
        ("is AR down", "AR"),
    ],
)
def test_status_questions_quote_the_named_asset(text, asset):
    turn, report = _plan(text)
    assert turn.status == "ready"
    assert turn.task.scope.assets == [asset]
    assert report["workflow"].steps[0].symbols == [asset]
    assert report["policy"].universe.symbols == [asset]


def test_compare_keeps_both_assets_and_the_window():
    turn, report = _plan("compare sol and eth over the last 7 days")
    assert turn.task.scope.assets == ["ETH", "SOL"] or set(turn.task.scope.assets) == {"ETH", "SOL"}
    assert turn.task.scope.window == "7d"
    assert any(step.type == "get_quotes_historical" for step in report["workflow"].steps)


def test_fell_the_most_ranks_declines_for_the_named_universe():
    turn, report = _plan("which of the top 20 coins fell the most")
    assert turn.status == "ready"
    assert turn.task.action == "rank_declines"
    assert turn.task.scope.listing_limit == 20
    assert turn.task.scope.assets == []
    present = next(step for step in report["workflow"].steps if step.type == "present")
    assert present.operation == "losers"


def test_up_the_most_ranks_gainers():
    turn, report = _plan("who is up the most today")
    assert turn.task.action == "rank_gains"
    present = next(step for step in report["workflow"].steps if step.type == "present")
    assert present.operation == "gainers"


def test_a_rise_is_not_stored_as_a_drop():
    turn, report = _plan("Watch ETH and tell me when it rises more than 3%.")
    condition = turn.task.trigger.conditions[0]
    assert condition["asset"] == "ETH"
    assert condition["operator"] == ">="
    assert condition["value"] == 3
    assert report["workflow"].trigger.asset == "ETH"
    assert report["workflow"].trigger.value == 3


def test_a_drop_watch_stays_negative():
    turn, report = _plan("when sol drops 5% tell me")
    condition = turn.task.trigger.conditions[0]
    assert condition["asset"] == "SOL"
    assert condition["operator"] == "<="
    assert condition["value"] == -5
    assert report["workflow"].steps[0].symbols == ["SOL"]


def test_unknown_text_does_not_become_a_bitcoin_quote():
    turn, _report = _plan("asdf qwerty")
    assert turn.status == "needs_input"
    assert turn.task.scope.assets == []
    assert "BTC" not in (turn.question or "")


def test_volume_question_does_not_invent_bitcoin():
    turn, _report = _plan("which coin has the highest volume")
    assert turn.status == "needs_input"
    assert turn.task.scope.assets == []
    assert "24h price change" in turn.question
    assert "Bitcoin" not in turn.question


def test_capability_and_keep_watching_are_commands():
    assert ConversationService.command("what can you do for me") == "capabilities"
    assert ConversationService.command("please keep watching this") == "watch"
