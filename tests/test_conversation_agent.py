from apps.intelligence.compiler import HeuristicCompiler
from apps.intelligence.conversation_agent import ConversationAgent, _task_from_llm
from apps.intelligence.job import JobDefinition
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


def test_eth_now_is_eth_even_after_a_btc_job():
    turn = ConversationAgent.understand(
        "what is ETH doing right now",
        current_job=JobDefinition(purpose="Report how BTC is doing from live CMC quotes.", execution_model="task"),
    )
    assert turn.task.scope.assets == ["ETH"]
    btc_policy = HeuristicCompiler().compile("how is bitcoin doing on the market today")
    report = compile_from_task(turn.task, current_policy=btc_policy)
    assert report["workflow"].steps[0].symbols == ["ETH"]
    assert report["job"].purpose.lower().startswith("report how eth")


def test_named_asset_in_message_beats_llm_copied_btc():
    task = _task_from_llm(
        "what is ETH doing right now",
        {"assets": ["BTC"], "mode": "ask", "task_type": "one_shot_research"},
    )
    assert task.scope.assets == ["ETH"]


def test_highest_gains_is_a_listings_rank_not_btc():
    text = "find me the coins with the highest gains within 24hrs"
    turn = ConversationAgent.understand(text)
    assert turn.status == "ready"
    assert turn.task.mode == "ask"
    assert turn.task.scope.assets == []
    assert turn.task.scope.universe.startswith("top")
    report = compile_from_task(turn.task)
    assert report["job"].is_persistent() is False
    assert report["workflow"].steps[0].type == "get_universe"
    sort = next(step for step in report["workflow"].steps if step.type == "sort")
    assert sort.order == "descending"
    present = next(step for step in report["workflow"].steps if step.type == "present")
    assert present.format == "ranked_table"
    assert present.operation == "gainers"


def test_llm_cannot_turn_highest_gains_into_a_btc_watch():
    from apps.intelligence.conversation_agent import _apply_movers_override

    task = _task_from_llm(
        "find me the coins with the highest gains within 24hrs",
        {
            "assets": ["BTC"],
            "mode": "work",
            "task_type": "persistent_monitor",
            "universe": "symbols",
        },
    )
    task = _apply_movers_override("find me the coins with the highest gains within 24hrs", task)
    assert task.mode == "ask"
    assert task.scope.assets == []
    assert task.scope.universe.startswith("top")


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
