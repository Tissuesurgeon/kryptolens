from apps.intelligence.conversation_agent import ConversationAgent
from apps.intelligence.task_compiler import compile_from_task


def test_compare_btc_eth_30d_is_ready_ask():
    turn = ConversationAgent.understand("Compare BTC and ETH over the last 30 days.")
    assert turn.status == "ready"
    assert turn.task.mode == "ask"
    assert "historical" in turn.task.capabilities
    assert "market" in turn.task.capabilities


def test_how_is_btc_is_ready_ask():
    turn = ConversationAgent.understand("How is BTC doing?")
    assert turn.status == "ready"
    assert turn.task.mode == "ask"


def test_watch_unusual_needs_input():
    turn = ConversationAgent.understand("Watch BTC for unusual activity.")
    assert turn.status == "needs_input"
    assert "significant" in turn.question.lower() or "price" in turn.question.lower()


def test_watch_important_needs_input_then_ready():
    first = ConversationAgent.understand("Watch BTC and tell me when something important happens.")
    assert first.status == "needs_input"
    second = ConversationAgent.understand(
        "a 3% drop",
        pending={"task": first.task.model_dump(mode="json"), "pending_field": first.task.pending_field},
    )
    assert second.status == "ready"
    assert second.task.mode == "work"
    assert second.task.trigger.conditions


def test_golden_watch_is_ready_immediately():
    turn = ConversationAgent.understand("When BTC drops by 2%, check the top 100 coins and rank their declines.")
    assert turn.status == "ready"
    assert turn.task.mode == "work"
    report = compile_from_task(turn.task)
    assert report["job"].is_persistent() is True
