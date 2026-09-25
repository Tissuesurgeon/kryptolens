"""Conversational analyst: research task, context, planner, evidence, and watch."""

import pytest
from pydantic import ValidationError

from apps.intelligence.agent import ChiefAgent
from apps.intelligence.capability_plan import CapabilityPlan
from apps.intelligence.clarified_task import ClarifiedTask, TaskScope, TaskTrigger
from apps.intelligence.conversation_agent import ConversationAgent
from apps.intelligence.job_compiler import workflow_from_task
from apps.intelligence.research.context import ResearchContext, resolve_follow_up
from apps.intelligence.research.finding import finding_from_result
from apps.intelligence.research.planner import ResearchPlanner
from apps.intelligence.research.task import ResearchTask
from apps.intelligence.response import compose_reply
from apps.intelligence.task_compiler import compile_from_task
from apps.lenses.agent_service import AgentService
from apps.lenses.conversation_service import ConversationService
from apps.users.models import User


def _context(assets, window="30d"):
    task = ResearchTask(
        assets=list(assets),
        window=window,
        objective=f"Compare {' and '.join(assets)}",
        capabilities=["historical", "market"],
        source_text="Compare BTC and ETH over the last 30 days.",
        mode="ask",
    )
    ctx = ResearchContext(active_entities=list(assets), timeframe=window)
    ctx.apply_task(task)
    return ctx


def test_planner_rejects_unknown_capability_and_tool():
    with pytest.raises(ValidationError):
        CapabilityPlan(capabilities=["dex"], tools=["get_quotes"])
    with pytest.raises(ValidationError):
        CapabilityPlan(capabilities=["market"], tools=["get_secret_feed"])


def test_research_planner_returns_plan_and_capability_plan():
    task = ResearchTask(
        assets=["ETH"],
        capabilities=["market"],
        objective="Report how ETH is doing",
        source_text="How is ETH doing?",
    )
    research_plan, capability_plan = ResearchPlanner().plan(task)
    assert research_plan.steps
    assert capability_plan.capabilities == ["market"]
    assert "get_quotes" in capability_plan.tools
    assert isinstance(ChiefAgent(), ResearchPlanner)


def test_follow_up_adds_sol_and_keeps_period():
    ctx = _context(["BTC", "ETH"])
    added = resolve_follow_up("Now add SOL", ctx)
    assert added.status == "ready"
    assert added.task.scope.assets == ["BTC", "ETH", "SOL"]
    assert added.task.scope.window == "30d"
    same = resolve_follow_up("Use the same period", ctx)
    assert same.task.scope.window == "30d"
    assert "BTC" in same.task.scope.assets


def test_unusual_follow_up_stays_on_the_current_assets():
    ctx = _context(["ETH"], window="")
    turn = resolve_follow_up("Was that unusual?", ctx)
    assert turn.task.scope.assets == ["ETH"]
    assert "anomaly" in turn.task.capabilities
    assert turn.task.scope.assets != ["BTC"]


def test_unknown_follow_up_does_not_become_a_btc_quote():
    ctx = _context(["ETH"], window="")
    turn = resolve_follow_up("asdf qwerty", ctx)
    assert turn.status == "needs_input"
    assert turn.task.scope.assets == ["ETH"]


def test_compiler_uses_task_assets_not_the_follow_up_sentence():
    task = ClarifiedTask(
        source_text="now add SOL",
        objective="Continue research on BTC and ETH and SOL",
        scope=TaskScope(assets=["BTC", "ETH", "SOL"], window="30d"),
        capabilities=["historical", "market"],
    )
    plan = ChiefAgent().plan_from_task(task)
    report = compile_from_task(task, capability_plan=plan)
    symbols = report["policy"].universe.symbols
    assert symbols[:3] == ["BTC", "ETH", "SOL"]


@pytest.mark.parametrize("asset", ["BTC", "ETH", "SOL"])
def test_reaction_workflow_uses_the_trigger_asset(asset):
    task = ClarifiedTask(
        mode="work",
        task_type="watch_plus_investigate",
        action="investigate_market_reaction",
        capabilities=["reaction", "market"],
        scope=TaskScope(assets=[asset], universe="top_100", listing_limit=100),
        trigger=TaskTrigger(conditions=[{"metric": "price_change_24h", "operator": "<=", "value": -2, "asset": asset}]),
        source_text=f"When {asset} drops by 2%, rank the top 100.",
    )
    workflow = workflow_from_task(task)
    assert workflow.trigger.asset == asset


def test_unsupported_quantitative_finding_is_not_a_confident_reply():
    class Result:
        id = 9
        kind = "quote"
        title = "Bitcoin is at $84000"
        payload_json = {"claims": ["Bitcoin is at $84000"], "metrics": {"price": 84000}}

    finding = finding_from_result(Result(), {"status": "unsupported"}, [])
    assert finding.quantitative
    assert finding.supported is False
    reply = compose_reply(Result(), {"status": "unsupported"})
    assert "could not support" in reply.lower()
    assert "84000" not in reply


def test_supported_finding_keeps_the_claim():
    class Result:
        id = 3
        kind = "quote"
        title = "ETH is up 1%"
        payload_json = {"claims": ["ETH is up 1%"], "metrics": {"price_change_24h": 1}}

    class Evidence:
        claim = "ETH quote from CoinMarketCap"
        observation_id = 4

    finding = finding_from_result(Result(), {"status": "supported"}, [Evidence()])
    assert finding.supported
    assert finding.observation_ids == [4]
    assert "CoinMarketCap" in finding.evidence[0]


@pytest.mark.django_db
def test_conversation_follow_up_and_keep_watching_stay_on_the_analyst():
    user = User.objects.create_user(username="analyst", email="analyst@kryptolens.app", password="Workspace-secret-99")
    other = User.objects.create_user(username="other", email="other@kryptolens.app", password="Workspace-secret-99")
    lens = AgentService.create(user, "Ada", "")
    foreign = AgentService.create(other, "Other", "")
    first = ConversationService.handle(lens, "Compare BTC and ETH over the last 30 days.")
    assert first.kind == "run"
    lens.refresh_from_db()
    added = ConversationService.handle(lens, "Now add SOL")
    assert added.kind == "run"
    lens.refresh_from_db()
    entities = lens.context_json["research"]["active_entities"]
    assert entities == ["BTC", "ETH", "SOL"]
    unknown = ConversationService.handle(lens, "asdf qwerty")
    assert unknown.kind == "needs_input"
    lens.refresh_from_db()
    assert lens.context_json["research"]["active_entities"] == ["BTC", "ETH", "SOL"]
    watched = ConversationService.handle(lens, "keep watching this")
    assert watched.kind == "run"
    lens.refresh_from_db()
    assert lens.current_routine() is not None
    assert lens.routines.count() == 1
    assert foreign.current_routine() is None
    html = ConversationService.context(lens)
    assert html["composer_placeholder"].startswith("Ask Ada")
    assert html["research_plan"]["steps"]


def test_heuristic_clarification_is_not_a_btc_default():
    turn = ConversationAgent.understand("hello there")
    assert turn.status == "needs_input"
    assert turn.task.scope.assets == []
