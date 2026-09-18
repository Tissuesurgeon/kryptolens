import pytest
from pydantic import ValidationError

from apps.intelligence.agent import ChiefAgent
from apps.intelligence.capability_plan import CapabilityPlan
from apps.intelligence.clarified_task import ClarifiedTask, TaskScope, TaskTrigger
from apps.intelligence.workflow import WorkflowDefinition, WorkflowStep, WorkflowTrigger


def test_valid_single_capability():
    plan = CapabilityPlan(
        capabilities=["market"],
        tools=["get_quotes"],
        reason="Live quote snapshot.",
        verification_requirements=["required_fields_present"],
    )
    assert plan.capabilities == ["market"]
    assert "get_quotes" in plan.tools


def test_valid_multiple_capabilities():
    plan = CapabilityPlan(
        capabilities=["market", "reaction"],
        tools=["get_quotes", "get_market_listings"],
        workflow=WorkflowDefinition(
            trigger=WorkflowTrigger(type="asset_condition", asset="ETH", value=-2),
            steps=[
                WorkflowStep(type="get_universe", limit=100),
                WorkflowStep(type="sort", field="price_change_24h", order="ascending"),
            ],
        ),
        reason="ETH trigger plus listings.",
        verification_requirements=["verify_trigger", "verify_rank_order"],
    )
    assert set(plan.capabilities) == {"market", "reaction"}
    assert "verify_trigger" in plan.verification_requirements


def test_invalid_capability_rejected():
    with pytest.raises(ValidationError, match="unknown capability"):
        CapabilityPlan(capabilities=["dex"], tools=["get_quotes"])


def test_invented_tool_rejected():
    with pytest.raises(ValidationError, match="invented tool|unknown tool"):
        CapabilityPlan(capabilities=["market"], tools=["invented_quotes"])


def test_incompatible_tool_rejected():
    with pytest.raises(ValidationError, match="unavailable"):
        CapabilityPlan(capabilities=["market"], tools=["get_quotes_historical"])


def test_invalid_workflow_rejected():
    with pytest.raises((ValidationError, ValueError)):
        CapabilityPlan(
            capabilities=["market"],
            tools=["get_quotes"],
            workflow={"steps": [{"type": "eval"}]},
        )


def test_verification_requirements_round_trip():
    plan = CapabilityPlan(
        capabilities=["market", "reaction"],
        tools=["get_quotes", "get_market_listings", "get_global_metrics"],
        verification_requirements=["verify_trigger", "verify_rank_order", "verify_percentage_calculations"],
    )
    assert plan.verification_requirements[0] == "verify_trigger"


def test_chief_selects_market_for_snapshot():
    task = ClarifiedTask(
        mode="ask",
        task_type="one_shot_research",
        objective="Report how BTC is doing",
        scope=TaskScope(assets=["BTC"]),
        capabilities=["market"],
        source_text="What's happening in crypto right now?",
    )
    plan = ChiefAgent().plan_from_task(task)
    assert plan.capabilities == ["market"]
    assert "get_quotes" in plan.tools


def test_chief_selects_anomaly_for_monitor():
    task = ClarifiedTask(
        mode="work",
        task_type="persistent_monitor",
        objective="Watch BTC for unusual activity",
        scope=TaskScope(assets=["BTC"]),
        capabilities=["anomaly", "market"],
        source_text="Watch BTC for unusual activity.",
    )
    plan = ChiefAgent().plan_from_task(task)
    assert "anomaly" in plan.capabilities
    assert "market" in plan.capabilities


def test_chief_selects_reaction_for_watch_plus():
    task = ClarifiedTask(
        mode="work",
        task_type="watch_plus_investigate",
        action="investigate_market_reaction",
        objective="When ETH drops 2%, rank declines",
        scope=TaskScope(assets=["ETH"], universe="top_100", listing_limit=100),
        trigger=TaskTrigger(conditions=[{"metric": "price_change_24h", "operator": "<=", "value": -2, "asset": "ETH"}]),
        capabilities=["market", "reaction"],
        source_text="When ETH drops 2%, rank the top 100 declines.",
    )
    plan = ChiefAgent().plan_from_task(task)
    assert "market" in plan.capabilities
    assert "reaction" in plan.capabilities
    assert plan.workflow.trigger.asset == "ETH"


def test_chief_selects_historical():
    task = ClarifiedTask(
        mode="ask",
        task_type="one_shot_research",
        objective="Compare BTC and ETH over 30d",
        scope=TaskScope(assets=["BTC", "ETH"], window="30d"),
        capabilities=["historical", "market"],
        source_text="Compare BTC and ETH over the last 30 days.",
    )
    plan = ChiefAgent().plan_from_task(task)
    assert "historical" in plan.capabilities
    assert "get_quotes_historical" in plan.tools


def test_chief_multi_capability_from_task_fields():
    task = ClarifiedTask(
        mode="work",
        task_type="watch_plus_investigate",
        action="investigate_market_reaction",
        objective="When BTC drops 3%, investigate a broad selloff versus previous events.",
        scope=TaskScope(assets=["BTC"], universe="top_100", window="30d", listing_limit=100),
        trigger=TaskTrigger(conditions=[{"metric": "price_change_24h", "operator": "<=", "value": -3, "asset": "BTC"}]),
        capabilities=["market", "reaction", "historical"],
        source_text="When BTC drops 3%, investigate whether it was a broad market selloff and compare it with previous similar events.",
    )
    plan = ChiefAgent().plan_from_task(task)
    assert set(plan.capabilities) >= {"market", "reaction", "historical"}
