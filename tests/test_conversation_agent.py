from apps.intelligence.compiler import HeuristicCompiler
from apps.intelligence.conversation_agent import ConversationAgent, _task_from_llm
from apps.intelligence.job import JobDefinition
from apps.intelligence.task_compiler import compile_from_task


class _JsonStub:
    def __init__(self, payload: str):
        self.payload = payload

    def generate(self, prompt, kind=""):
        _ = prompt
        return self.payload


def test_compare_btc_eth_30d_is_ready_ask():
    turn = ConversationAgent.understand("Compare BTC and ETH over the last 30 days.")
    assert turn.status == "ready"
    assert turn.task.mode == "ask"
    assert "historical" in turn.task.capabilities
    assert "market" in turn.task.capabilities


def test_how_is_ar_doing_uses_ar_not_btc():
    turn = ConversationAgent.understand("how is AR doing ?")
    assert turn.status == "ready"
    assert turn.task.scope.assets == ["AR"]
    report = compile_from_task(turn.task)
    assert report["policy"].universe.symbols == ["AR"]
    assert report["workflow"].steps[0].symbols == ["AR"]
    replaced = _task_from_llm(
        "how is AR doing ?",
        {"assets": ["BTC"], "mode": "ask", "task_type": "one_shot_research", "objective": "Report how BTC is doing"},
    )
    assert replaced.scope.assets == ["AR"]


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


def test_llm_assets_are_not_overwritten_by_heuristics():
    task = _task_from_llm(
        "what is ETH doing right now",
        {"assets": ["ETH"], "mode": "ask", "task_type": "one_shot_research"},
    )
    assert task.scope.assets == ["ETH"]


def test_empty_llm_assets_fill_from_the_message():
    task = _task_from_llm(
        "what is ETH doing right now",
        {"assets": [], "mode": "ask", "task_type": "one_shot_research"},
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


def test_heuristic_highest_gains_is_ranked_table_ask():
    turn = ConversationAgent.understand("find me the coins with the highest gains within 24hrs")
    assert turn.task.mode == "ask"
    assert turn.task.action == "rank_gains"
    assert turn.task.requested_output == "ranked_table"
    assert turn.task.scope.assets == []
    assert turn.task.scope.universe.startswith("top")


def test_stubbed_llm_highest_gains_is_respected():
    class Stub:
        def generate(self, prompt, kind=""):
            return """{
              "status": "ready",
              "mode": "ask",
              "task_type": "one_shot_research",
              "assets": [],
              "universe": "top_100",
              "action": "rank_gains",
              "requested_output": "ranked_table",
              "capabilities": ["market"]
            }"""

    turn = ConversationAgent.understand(
        "find me the coins with the highest gains within 24hrs",
        provider=Stub(),
    )
    assert turn.status == "ready"
    assert turn.task.mode == "ask"
    assert turn.task.action == "rank_gains"
    assert turn.task.requested_output == "ranked_table"


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
    assert report["workflow"].trigger.asset == "BTC"
    assert report["workflow"].trigger.value == -2.0


def test_eth_reaction_uses_eth_trigger():
    text = "When ETH drops by 2%, check all the top 100 coins and list their declines from biggest to smallest."
    turn = ConversationAgent.understand(text)
    assert turn.status == "ready"
    assert turn.task.mode == "work"
    assert turn.task.trigger_asset() == "ETH"
    assert "reaction" in turn.task.capabilities
    report = compile_from_task(turn.task)
    assert report["job"].is_persistent() is True
    assert report["workflow"].trigger.asset == "ETH"
    assert report["workflow"].trigger.value == -2.0
    assert report["workflow"].steps[0].limit == 100
    sort = next(step for step in report["workflow"].steps if step.type == "sort")
    assert sort.order == "ascending"


def test_stubbed_llm_unusual_clarification_then_ready():
    first = ConversationAgent.understand(
        "Watch BTC for unusual activity.",
        provider=_JsonStub(
            """{
              "status": "needs_input",
              "question": "What should count as unusual activity — a large price move, unusual volume, or both?",
              "pending_field": "unusual_definition",
              "mode": "work",
              "task_type": "persistent_monitor",
              "assets": ["BTC"],
              "capabilities": ["anomaly", "market"]
            }"""
        ),
    )
    assert first.status == "needs_input"
    assert first.question
    assert first.task is not None
    assert first.task.pending_field
    second = ConversationAgent.understand(
        "Consider a 3% move with unusually high volume.",
        pending={"task": first.task.model_dump(mode="json"), "pending_field": first.task.pending_field},
        provider=_JsonStub(
            """{
              "status": "ready",
              "mode": "work",
              "task_type": "persistent_monitor",
              "assets": ["BTC"],
              "action": "notify",
              "trigger_conditions": [
                {"metric": "price_change_24h", "operator": ">=", "value": 3, "asset": "BTC"},
                {"metric": "volume_change_24h", "operator": ">=", "value": 80, "asset": "BTC"}
              ],
              "capabilities": ["anomaly", "market"]
            }"""
        ),
    )
    assert second.status == "ready"
    assert second.task.mode == "work"
    assert second.task.trigger.conditions


def test_compare_now_is_one_shot():
    turn = ConversationAgent.understand("Compare BTC and ETH right now.")
    assert turn.status == "ready"
    assert turn.task.mode == "ask"
    report = compile_from_task(turn.task)
    assert report["job"].is_persistent() is False
    assert report["job"].routine_kind is None


def test_btc_drop_highest_drop_is_reaction_watch_not_gains():
    text = "when btc drops by 2%, find me the coins with the highest drop"
    turn = ConversationAgent.understand(text)
    assert turn.status == "ready"
    assert turn.task.mode == "work"
    assert turn.task.task_type == "watch_plus_investigate"
    report = compile_from_task(turn.task)
    assert report["job"].is_persistent() is True
    assert report["workflow"].trigger.asset == "BTC"
    assert report["workflow"].trigger.value == -2.0
    assert report["workflow"].steps[0].type == "get_universe"
    sort = next(step for step in report["workflow"].steps if step.type == "sort")
    assert sort.order == "ascending"
    assert not any(step.type == "filter" and step.operator == ">" for step in report["workflow"].steps)


def test_highest_drop_watch_does_not_keep_a_prior_gains_filter():
    gains = ConversationAgent.understand("find me the coins with the highest gains within 24hrs")
    gain_report = compile_from_task(gains.task)
    drop = ConversationAgent.understand("when btc drops by 2%, find me the coins with the highest drop")
    report = compile_from_task(
        drop.task,
        current_policy=gain_report["policy"],
        current_workflow=gain_report["workflow"],
    )
    assert report["workflow"].trigger.value == -2.0
    sort = next(step for step in report["workflow"].steps if step.type == "sort")
    assert sort.order == "ascending"
    assert not any(step.type == "filter" and step.operator == ">" for step in report["workflow"].steps)


def test_reply_answers_the_user_message_from_verified_numbers():
    from types import SimpleNamespace

    from apps.intelligence.response import compose_reply

    class Stub:
        def __init__(self):
            self.prompt = ""

        def generate(self, prompt, kind=""):
            self.prompt = prompt
            return "AR is at $12.50, up 1.20% over 24 hours."

    result = SimpleNamespace(
        kind="comparison",
        title="AR",
        payload_json={"rows": [{"symbol": "AR", "name": "Arweave", "price": 12.5, "price_change_24h": 1.2}]},
    )
    provider = Stub()
    text = compose_reply(
        result,
        provider=provider,
        task={"you_asked": ["how is AR doing ?"], "scope": {"assets": ["AR"]}, "source_text": "how is AR doing ?"},
    )
    assert "how is AR doing" in provider.prompt
    assert "AR is at $12.50" in text
    assert "Bitcoin" not in text


def test_reply_rejects_a_number_the_data_does_not_contain():
    from types import SimpleNamespace

    from apps.intelligence.response import compose_reply

    class Stub:
        def generate(self, prompt, kind=""):
            return "AR is at $99999.00, up 1.20% over 24 hours."

    result = SimpleNamespace(
        kind="comparison",
        title="AR",
        payload_json={"rows": [{"symbol": "AR", "name": "Arweave", "price": 12.5, "price_change_24h": 1.2}]},
    )
    text = compose_reply(
        result,
        provider=Stub(),
        task={"you_asked": ["how is AR doing ?"], "scope": {"assets": ["AR"]}},
    )
    assert "99999" not in text
    assert "12.50" in text or "12.5" in text


def test_reply_does_not_quote_a_different_asset():
    from types import SimpleNamespace

    from apps.intelligence.response import compose_reply

    result = SimpleNamespace(
        kind="comparison",
        title="Bitcoin",
        payload_json={"rows": [{"symbol": "BTC", "name": "Bitcoin", "price": 84559.92, "price_change_24h": 0.61}]},
    )
    text = compose_reply(result, task={"you_asked": ["how is AR doing ?"], "scope": {"assets": ["AR"]}})
    assert "AR" in text
    assert "84559" not in text.replace(",", "")
    assert "Bitcoin" not in text


def test_no_result_reply_stays_grounded():
    from types import SimpleNamespace

    from apps.intelligence.response import compose_reply

    result = SimpleNamespace(kind="no_result", title="Quiet", payload_json={})
    text = compose_reply(result)
    assert "CoinMarketCap" in text
    assert "No matching" in text
