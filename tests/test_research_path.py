"""The research turn has one planner: ResearchTask → ResearchPlanner → CapabilityPlan."""

import inspect

import pytest
from pydantic import ValidationError

from apps.intelligence.capability_plan import CapabilityPlan, CapabilityPlanError
from apps.intelligence.conversation_agent import ConversationAgent
from apps.intelligence.job_compiler import workflow_from_task
from apps.intelligence.research.context import ResearchContext, resolve_follow_up
from apps.intelligence.research.finding import Finding
from apps.intelligence.research.planner import ResearchPlanner
from apps.intelligence.research.task import ResearchTask
from apps.intelligence.response import compose_reply
from apps.intelligence.task_compiler import compile_from_task
from apps.lenses.conversation_service import ConversationService


class _Json:
    def __init__(self, payload: str):
        self.payload = payload

    def generate(self, prompt, kind=""):
        _ = prompt, kind
        return self.payload


def _research(text: str, **kwargs) -> ResearchTask:
    turn = ConversationAgent.understand(text, **kwargs)
    assert turn.status == "ready", turn.question
    assert turn.research
    return ResearchTask.model_validate(turn.research)


def test_top_10_uses_one_planner_and_no_btc_step():
    task = _research("What are the top 10 cryptocurrencies by market cap right now?")
    assert task.listing_limit == 10
    assert task.assets == []
    research_plan, capability_plan = ResearchPlanner().plan(task)
    assert research_plan.capabilities
    assert "market" in capability_plan.capabilities
    report = compile_from_task(task, capability_plan=capability_plan)
    assert report["workflow"].steps[0].type == "get_universe"
    assert report["workflow"].steps[0].limit == 10
    projected = capability_plan.to_agent_plan(objective=task.objective)
    assert projected.specialist is None
    assert "check_btc" not in projected.steps


def test_historical_btc_uses_the_same_planner():
    task = _research("How did BTC perform during 2024?")
    assert task.assets == ["BTC"]
    assert task.window == "2024"
    assert "historical" in task.capabilities
    _, capability_plan = ResearchPlanner().plan(task)
    assert "historical" in capability_plan.capabilities
    assert capability_plan.to_agent_plan().specialist is None
    assert "check_btc" not in capability_plan.to_agent_plan().steps


def test_compare_names_both_assets_and_the_window():
    task = _research("Compare BTC and ETH over the last 30 days.")
    assert set(task.assets) == {"BTC", "ETH"}
    assert task.window == "30d"
    _, capability_plan = ResearchPlanner().plan(task)
    assert "historical" in capability_plan.capabilities


def test_add_sol_keeps_the_comparison_window():
    first = _research("Compare BTC and ETH over the last 30 days.")
    context = ResearchContext()
    context.apply_task(first, {"objective": first.objective})
    added = resolve_follow_up("Now add SOL", context)
    assert added is not None and added.research
    task = ResearchTask.model_validate(added.research)
    assert set(task.assets) == {"BTC", "ETH", "SOL"}
    assert task.window == "30d"


def test_now_do_sol_keeps_the_same_period():
    first = _research("Compare BTC and ETH over the last 30 days.")
    context = ResearchContext()
    context.apply_task(first, {"objective": first.objective})
    followed = resolve_follow_up("Now do SOL", context)
    assert followed is not None and followed.research
    task = ResearchTask.model_validate(followed.research)
    assert task.assets == ["SOL"]
    assert task.window == "30d"
    assert "historical" in task.capabilities


def test_missing_asset_is_not_compiled_as_bitcoin():
    task = ResearchTask(objective="Quote the market", action="report", source_text="hello there")
    workflow = workflow_from_task(task.to_clarified())
    assert workflow.steps == []
    report = compile_from_task(task)
    for step in report["workflow"].steps:
        assert "BTC" not in (step.symbols or [])
    assert (report["workflow"].trigger is None) or report["workflow"].trigger.asset != "BTC"


def test_valid_llm_task_beats_a_reaction_heuristic():
    sentence = "When ETH drops by 2%, analyze the top 10"
    heuristic = ConversationAgent.understand(sentence)
    assert heuristic.task.task_type == "watch_plus_investigate"
    turn = ConversationAgent.understand(
        sentence,
        provider=_Json(
            """{
              "status": "ready",
              "mode": "ask",
              "task_type": "one_shot_research",
              "assets": ["ETH"],
              "objective": "Report how ETH is doing",
              "capabilities": ["market"]
            }"""
        ),
    )
    task = ResearchTask.model_validate(turn.research)
    assert task.assets == ["ETH"]
    assert task.task_type == "one_shot_research"
    assert task.mode == "ask"


def test_conversation_turn_does_not_call_a_second_planner():
    source = inspect.getsource(ConversationService._turn)
    assert "compile_job_report" not in source
    assert "plan_from_text" not in source
    assert "build_agent_plan" not in source
    assert "ChiefAgent" not in source
    planner = inspect.getsource(ResearchPlanner.plan)
    assert "compile_job_report" not in planner
    assert "specialist" not in planner
    runtime = inspect.getsource(__import__("apps.intelligence.agent_runtime", fromlist=["_plan_for_run"])._plan_for_run)
    assert "capability_plan" in runtime
    assert "plan_from_text" not in runtime


def test_capability_plan_rejects_an_incompatible_tool():
    with pytest.raises((CapabilityPlanError, ValidationError)):
        CapabilityPlan(capabilities=["historical"], tools=["get_trending"])


def test_unsupported_finding_is_not_a_conclusion():
    finding = Finding(
        claim="Bitcoin is at $84000",
        verification="unsupported",
        quantitative=True,
        supported=False,
    )
    assert finding.grounded() is False
    inconclusive = Finding(claim="ETH is up 4%", verification="needs_more_evidence", supported=False)
    assert inconclusive.grounded() is False

    class Result:
        id = 1
        kind = "quote"
        title = "Bitcoin is at $84000"
        payload_json = {"claims": ["Bitcoin is at $84000"], "metrics": {"price": 84000}}

    reply = compose_reply(Result(), {"status": "unsupported"})
    assert "84000" not in reply
    assert "could not support" in reply.lower()
