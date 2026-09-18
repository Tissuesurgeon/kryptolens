import json

from apps.intelligence.agent import ChiefAgent
from apps.intelligence.job_compiler import compile_job_report
from apps.intelligence.llm import HeuristicProvider
from apps.intelligence.understanding import Understanding, materialize_understanding, understand_with_llm


class FakeUnderstandProvider:
    def __init__(self, payload: dict):
        self.payload = payload
        self.prompts: list[str] = []

    def generate(self, prompt: str, **kwargs) -> str:
        self.prompts.append(prompt)
        return json.dumps(self.payload)


def test_llm_understands_bitcoin_today_as_snapshot():
    provider = FakeUnderstandProvider(
        {
            "you_asked": ["how is bitcoin doing on the market today"],
            "assumptions": ["Interpreted bitcoin as BTC."],
            "kind": "snapshot",
            "name": "BTC now",
            "purpose": "Report how BTC is doing from live CMC quotes.",
            "symbols": ["BTC"],
            "listing_limit": None,
            "execution_model": "task",
            "routine_kind": None,
            "trigger": None,
            "present": "comparison",
            "news_unavailable": False,
        }
    )
    report = compile_job_report("how is bitcoin doing on the market today", provider=provider)
    assert provider.prompts
    assert "User message:" in provider.prompts[0]
    job = report["job"]
    workflow = report["workflow"]
    assert job.execution_model == "task"
    assert job.is_persistent() is False
    assert job.you_asked == ["how is bitcoin doing on the market today"]
    assert workflow.trigger is None
    assert [step.type for step in workflow.steps] == ["get_quotes", "present"]
    assert workflow.steps[0].symbols == ["BTC"]
    plan, planned = ChiefAgent().plan_from_text("how is bitcoin doing on the market today", provider=provider)
    assert plan.job_type == "investigate"
    assert "get_quotes" in plan.tools
    assert planned["job"].execution_model == "task"


def test_llm_understands_golden_as_watch_plus_workflow():
    provider = FakeUnderstandProvider(
        {
            "you_asked": [
                "When BTC drops by 2%",
                "Check the top 100 coins",
                "Rank them from biggest drop to smallest",
            ],
            "assumptions": ["Trigger is BTC 24h change <= -2%."],
            "kind": "watch_plus_workflow",
            "name": "BTC Reaction Watcher",
            "purpose": "Monitor Bitcoin and analyze how the broader market reacts.",
            "symbols": ["BTC"],
            "listing_limit": 100,
            "execution_model": "watch_plus_workflow",
            "routine_kind": "event_triggered",
            "trigger": {"asset": "BTC", "metric": "price_change_24h", "operator": "<=", "value": -2},
            "present": "ranked_table",
            "news_unavailable": False,
        }
    )
    report = compile_job_report(
        "When BTC drops by 2%, check the top 100 coins and rank their declines.",
        provider=provider,
    )
    job = report["job"]
    workflow = report["workflow"]
    assert job.execution_model == "watch_plus_workflow"
    assert workflow.trigger.asset == "BTC"
    assert workflow.trigger.value == -2
    assert [step.type for step in workflow.steps][-1] == "present"


def test_watch_without_trigger_becomes_snapshot():
    understanding = understand_with_llm(
        "how is bitcoin doing on the market today",
        FakeUnderstandProvider(
            {
                "kind": "watch",
                "you_asked": ["how is bitcoin doing on the market today"],
                "symbols": ["BTC"],
                "trigger": None,
                "execution_model": "watch",
                "routine_kind": "event_triggered",
            }
        ),
    )
    assert understanding.kind == "snapshot"
    job, workflow, _ = materialize_understanding("how is bitcoin doing on the market today", understanding)
    assert job.execution_model == "task"
    assert workflow.trigger is None


def test_heuristic_provider_still_compiles_offline():
    report = compile_job_report(
        "how is bitcoin doing on the market today",
        provider=HeuristicProvider(),
    )
    assert report["job"].execution_model == "task"
    assert Understanding.model_validate({"kind": "snapshot", "you_asked": ["x"]}).kind == "snapshot"


def test_news_question_short_circuits_llm_edit():
    provider = FakeUnderstandProvider(
        {
            "kind": "edit",
            "you_asked": ["top 100 assets"],
            "assumptions": ['"Biggest" / top interpreted as highest market-cap assets.'],
            "execution_model": "watch",
            "news_unavailable": False,
        }
    )
    from apps.intelligence.job import JobDefinition
    from apps.intelligence.workflow import WorkflowDefinition, WorkflowStep

    report = compile_job_report(
        "what news is affecting the crypto market today?",
        provider=provider,
        current_job=JobDefinition(purpose="ETH now", execution_model="task"),
        current_workflow=WorkflowDefinition(
            steps=[
                WorkflowStep(type="get_quotes", symbols=["ETH"]),
                WorkflowStep(type="present", format="comparison"),
            ]
        ),
    )
    assert report["job"].news_unavailable is False
    assert report["job"].is_persistent() is False
    assert [step.type for step in report["workflow"].steps] == ["get_content", "get_quotes", "present"]
    assert provider.prompts == []