import pytest

from apps.intelligence.conversation_agent import ConversationAgent
from apps.intelligence.job_compiler import compile_job_report
from apps.intelligence.llm import HeuristicProvider
from apps.intelligence.task_compiler import compile_from_task

CASES = [
    ("when BTC drops 2%, analyze the top 10", "BTC", "<=", -2.0, 10, "ascending"),
    ("when BTC drops 2%, analyze how it affects top 10 coins", "BTC", "<=", -2.0, 10, "ascending"),
    ("When BTC drops by 2%, check the top 100 coins and rank their declines.", "BTC", "<=", -2.0, 100, "ascending"),
    ("whenever bitcoin falls 5%, rank the top 20", "BTC", "<=", -5.0, 20, "ascending"),
    ("if ETH drops 3%, analyze the top 15 coins", "ETH", "<=", -3.0, 15, "ascending"),
    ("when SOL crashes 8%, show me the top 10", "SOL", "<=", -8.0, 10, "ascending"),
    ("when BTC drops 2% analyze top ten coins", "BTC", "<=", -2.0, 10, "ascending"),
    ("When XRP falls 4%, list the biggest drops in the top 25", "XRP", "<=", -4.0, 25, "ascending"),
    ("every time ETH dumps 6%, check the top 50", "ETH", "<=", -6.0, 50, "ascending"),
    ("if bitcoin is down 2 percent, analyze top 10", "BTC", "<=", -2.0, 10, "ascending"),
    ("when BTC drops two percent, look at the top 10", "BTC", "<=", -2.0, 10, "ascending"),
    ("BTC down 2% then analyze top 10", "BTC", "<=", -2.0, 10, "ascending"),
    ("once BTC falls 2%, what happens to the top 10", "BTC", "<=", -2.0, 10, "ascending"),
    ("when BTC drops 2.5%, analyze the top 10 altcoins", "BTC", "<=", -2.5, 10, "ascending"),
    ("analyze the top 10 when BTC drops 2%", "BTC", "<=", -2.0, 10, "ascending"),
    ("top 10 reaction if bitcoin falls more than 2%", "BTC", "<=", -2.0, 10, "ascending"),
    ("when LINK drops 7%, investigate the top 12", "LINK", "<=", -7.0, 12, "ascending"),
    ("if BTC loses 2%, check top 10", "BTC", "<=", -2.0, 10, "ascending"),
    ("whenever BTC is down 2 percent analyze top 10 coins", "BTC", "<=", -2.0, 10, "ascending"),
    ("when btc drops 2 % analyze the top 10", "BTC", "<=", -2.0, 10, "ascending"),
    ("pls when btc drops 2% can you analyze the top 10", "BTC", "<=", -2.0, 10, "ascending"),
    ("when DOGE falls 10%, rank the worst 15", "DOGE", "<=", -10.0, 15, "ascending"),
    ("after SOL drops 4% tell me how the top 10 reacted", "SOL", "<=", -4.0, 10, "ascending"),
    ("what happens to the top 10 if bitcoin drops 2%", "BTC", "<=", -2.0, 10, "ascending"),
    ("when ETH drops 2% vs BTC analyze the top 10", "ETH", "<=", -2.0, 10, "ascending"),
    ("when BTC rises 2%, analyze the top 10", "BTC", ">=", 2.0, 10, "descending"),
    ("when ETH pumps 4%, rank the top 10 gainers", "ETH", ">=", 4.0, 10, "descending"),
    ("alert me when BTC rises more than 5% and rank the top 30 gainers", "BTC", ">=", 5.0, 30, "descending"),
    ("when BTC climbs 3%, show the top 20 that gained the most", "BTC", ">=", 3.0, 20, "descending"),
    ("as soon as bitcoin dips 2%, look through the top 10", "BTC", "<=", -2.0, 10, "ascending"),
    ("when btc loses two percent, check the ten biggest coins", "BTC", "<=", -2.0, 10, "ascending"),
    ("when BTC gains 2%, analyze the top 10", "BTC", ">=", 2.0, 10, "descending"),
    ("the moment ETH falls 1.5%, analyze top 10", "ETH", "<=", -1.5, 10, "ascending"),
    ("if solana dumps 3 percent, show the worst 8", "SOL", "<=", -3.0, 8, "ascending"),
    ("should BTC slide 2%, rank the top 10 losers", "BTC", "<=", -2.0, 10, "ascending"),
]


@pytest.mark.parametrize("text,asset,operator,value,limit,order", CASES)
def test_reaction_phrase_waits_on_the_named_move(text, asset, operator, value, limit, order):
    turn = ConversationAgent.understand(text, provider=HeuristicProvider())
    assert turn.status == "ready"
    assert turn.task.task_type == "watch_plus_investigate"
    assert turn.task.mode == "work"
    condition = turn.task.trigger.conditions[0]
    assert condition["asset"] == asset
    assert condition["operator"] == operator
    assert condition["value"] == value
    assert turn.task.scope.listing_limit == limit
    workflow = compile_from_task(turn.task)["workflow"]
    assert workflow.trigger.asset == asset
    assert workflow.trigger.operator == operator
    assert workflow.trigger.value == value
    assert workflow.steps[0].limit == limit
    sort = next(step for step in workflow.steps if step.type == "sort")
    assert sort.order == order
    report = compile_job_report(text, provider=HeuristicProvider())
    assert report["job"].execution_model == "watch_plus_workflow"
    assert report["workflow"].trigger.asset == asset
    assert report["workflow"].trigger.value == value
    assert report["workflow"].steps[0].limit == limit
