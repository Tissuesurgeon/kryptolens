import json
from pathlib import Path

import httpx
import pytest
import respx

from apps.cmc.adapter import CMCAdapter
from apps.intelligence.calculations import rank_assets, run_calculation, sort_assets
from apps.intelligence.job_compiler import compile_job_report
from apps.intelligence.observations import MarketObservation
from apps.intelligence.tools import ToolPermissionError, require_tool
from apps.intelligence.workflow import validate_workflow_dict
from apps.lenses.models import ConversationItem, Result
from apps.lenses.runtime import LensRuntime
from apps.lenses.services import apply_intent_edit, create_lens_from_intent
from apps.users.models import User

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "listings_latest.json").read_text())
GOLDEN = "When BTC drops by 2%, check the top 100 coins and rank their declines."


def _btc_drop_payload(change: float):
    payload = json.loads(json.dumps(FIXTURE))
    payload["data"][0]["quote"]["USD"]["percent_change_24h"] = change
    return {
        "status": payload["status"],
        "data": {"BTC": payload["data"][0]},
    }


@pytest.mark.django_db
def test_how_is_bitcoin_doing_today_is_a_one_shot_quote_check():
    report = compile_job_report("how is bitcoin doing on the market today")
    job = report["job"]
    workflow = report["workflow"]
    assert job.execution_model == "task"
    assert job.routine_kind is None
    assert workflow.trigger is None
    assert [step.type for step in workflow.steps] == ["get_quotes", "present"]
    assert workflow.steps[0].symbols == ["BTC"]
    assert job.you_asked == ["how is bitcoin doing on the market today"]
    assert report["policy"].asset_conditions == []


@pytest.mark.django_db
def test_smallest_valid_compare_now_has_no_routine():
    user = User.objects.create_user(username="cmp", email="cmp@kryptolens.app", password="x")
    lens, version, _ = create_lens_from_intent(user, "Compare BTC and ETH right now.")
    job = version.as_job()
    assert job.execution_model == "task"
    assert job.routine_kind is None
    assert lens.routines.exists() is False
    assert version.workflow_json["steps"]


@pytest.mark.django_db
def test_golden_btc_job_compiles_routine_trigger_workflow():
    report = compile_job_report(GOLDEN)
    job = report["job"]
    workflow = report["workflow"]
    assert job.execution_model == "watch_plus_workflow"
    assert job.routine_kind == "event_triggered"
    assert workflow.trigger.asset == "BTC"
    assert workflow.trigger.value == -2
    assert [step.type for step in workflow.steps][-1] == "present"
    user = User.objects.create_user(username="btc", email="btc@kryptolens.app", password="x")
    lens, version, _ = create_lens_from_intent(user, GOLDEN)
    assert version.job_definition_json["execution_model"] == "watch_plus_workflow"
    assert lens.routines.filter(kind="event_triggered").exists()
    assert ConversationItem.objects.filter(lens=lens, item_type="job_created").exists()


def test_btc_reaction_honors_top_20():
    report = compile_job_report(
        "when bitcoin drops by 2%, check the top 20 coins and rank their declines"
    )
    job = report["job"]
    workflow = report["workflow"]
    assert report["policy"].universe.limit == 20
    assert "Check the top 20 coins" in job.you_asked
    assert job.workflow_summary == "Rank top 20 by 24h decline"
    assert workflow.steps[0].limit == 20
    assert workflow.steps[0].universe == "top_20"
    assert "Retrieve top_20" in workflow.explained_steps()
    assert "top 100" not in " ".join(job.you_asked).lower()


@pytest.mark.django_db
def test_news_request_compiles_content_and_quotes():
    report = compile_job_report("Create a news watcher.")
    job = report["job"]
    workflow = report["workflow"]
    assert job.news_unavailable is False
    assert job.execution_model == "scheduled"
    assert [step.type for step in workflow.steps] == ["get_content", "get_quotes", "present"]
    assert workflow.steps[-1].format == "news_brief"


def test_news_market_question_is_not_a_top100_watch():
    from apps.intelligence.job import JobDefinition
    from apps.intelligence.job_compiler import is_news_request
    from apps.intelligence.llm import HeuristicProvider
    from apps.intelligence.workflow import WorkflowDefinition, WorkflowStep

    text = "what news is affecting the crypto market today?"
    assert is_news_request(text)
    report = compile_job_report(text, provider=HeuristicProvider())
    job = report["job"]
    assert job.news_unavailable is False
    assert job.is_persistent() is False
    assert job.you_asked == [text]
    assert [step.type for step in report["workflow"].steps] == ["get_content", "get_quotes", "present"]

    current_job = JobDefinition(
        purpose="Report how ETH is doing from live CMC quotes.",
        execution_model="task",
        you_asked=["how is ETH doing on the market today"],
    )
    current_workflow = WorkflowDefinition(
        steps=[
            WorkflowStep(type="get_quotes", symbols=["ETH"]),
            WorkflowStep(type="present", format="comparison"),
        ]
    )
    follow = compile_job_report(
        text,
        provider=HeuristicProvider(),
        current_job=current_job,
        current_workflow=current_workflow,
    )
    assert follow["job"].news_unavailable is False
    assert follow["job"].is_persistent() is False
    assert follow["workflow"].steps[0].type == "get_content"


def test_workflow_rejects_unknown_and_code_steps():
    with pytest.raises(ValueError):
        validate_workflow_dict({"steps": [{"type": "eval"}]})
    with pytest.raises(ValueError):
        validate_workflow_dict({"steps": [{"type": "http"}]})


def test_tool_permission_denies_news_slot():
    with pytest.raises(ToolPermissionError):
        require_tool({"get_market_listings": True, "news": False}, "news")
    require_tool({"get_content": True}, "get_content")


def test_calculations_are_deterministic():
    observations = [
        MarketObservation(asset_id=1, symbol="AAA", price_change_24h=-8.7),
        MarketObservation(asset_id=2, symbol="BBB", price_change_24h=-2.1),
    ]
    ranked = rank_assets(observations, "price_change_24h", "ascending")
    assert ranked[0]["symbol"] == "AAA"
    assert sort_assets(observations, "price_change_24h", "ascending")[0].symbol == "AAA"
    with pytest.raises(ValueError):
        run_calculation("os.system")


@respx.mock
@pytest.mark.django_db
def test_golden_btc_run_now_persists_ranked_result():
    user = User.objects.create_user(username="run", email="run@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, GOLDEN)
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    run = LensRuntime(adapter=CMCAdapter(api_key="test-key")).run_now(lens.id)
    assert run.status == "ok"
    result = Result.objects.get(lens=lens)
    assert result.kind == "ranked_table"
    rows = result.payload_json["rows"]
    assert rows
    changes = [row["price_change_24h"] for row in rows]
    assert changes == sorted(changes)
    assert ConversationItem.objects.filter(lens=lens, item_type="scan_result").exists()
    listings = [call for call in respx.calls if "listings/latest" in str(call.request.url)]
    assert len(listings) == 1


@respx.mock
@pytest.mark.django_db
def test_trigger_routine_zero_result_when_btc_has_not_dropped():
    user = User.objects.create_user(username="trig", email="trig@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, GOLDEN)
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest").mock(
        return_value=httpx.Response(200, json=_btc_drop_payload(1.4))
    )
    run = LensRuntime(adapter=CMCAdapter(api_key="test-key")).trigger_routine(lens.id)
    assert run.status == "ok"
    result = Result.objects.get(lens=lens)
    assert result.kind == "no_result"


@respx.mock
@pytest.mark.django_db
def test_trigger_routine_ranks_when_btc_dropped():
    user = User.objects.create_user(username="fire", email="fire@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, GOLDEN)
    dropped = json.loads(json.dumps(FIXTURE))
    dropped["data"][0]["quote"]["USD"]["percent_change_24h"] = -3.1
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest").mock(
        return_value=httpx.Response(200, json=_btc_drop_payload(-3.1))
    )
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json=dropped)
    )
    run = LensRuntime(adapter=CMCAdapter(api_key="test-key")).trigger_routine(lens.id)
    assert run.status == "ok"
    result = Result.objects.get(lens=lens, kind="ranked_table")
    assert result.payload_json["rows"]
    assert ConversationItem.objects.filter(lens=lens, item_type="event_result").exists()


@respx.mock
@pytest.mark.django_db
def test_cmc_failure_is_error_result():
    user = User.objects.create_user(username="fail", email="fail@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, GOLDEN)
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(500, json={"status": {"error_message": "down"}})
    )
    run = LensRuntime(adapter=CMCAdapter(api_key="test-key")).run_now(lens.id)
    assert run.status == "error"
    assert Result.objects.filter(lens=lens, kind="error").exists()


@pytest.mark.django_db
def test_edit_creates_new_version_keeps_old_runs():
    user = User.objects.create_user(username="edit", email="edit@kryptolens.app", password="x")
    lens, v1, _ = create_lens_from_intent(user, GOLDEN)
    from apps.lenses.models import LensRun

    old_run = LensRun.objects.create(lens=lens, lens_version=v1, trigger="manual", status="ok", stage="complete")
    version, diffs = apply_intent_edit(lens, "Instead of top 100, use top 50 and only include assets that dropped more than BTC.")
    assert version.version == 2
    assert version.as_workflow().steps
    assert any(step.relative_to == "BTC" or (step.limit == 50) for step in version.as_workflow().steps)
    old_run.refresh_from_db()
    assert old_run.lens_version_id == v1.id
    assert diffs
    item = ConversationItem.objects.filter(lens=lens, item_type="policy_diff").latest("id")
    assert item.payload_json["diffs"]
    assert item.payload_json["version"] == 2


@pytest.mark.django_db
def test_morning_brief_sets_schedule_time(monkeypatch):
    from datetime import datetime, time

    from django.utils import timezone as djtz

    from apps.monitoring.tasks import _should_run
    import apps.monitoring.tasks as tasks

    user = User.objects.create_user(username="morn", email="morn@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, "Every morning summarize major crypto changes.")
    lens.status = "active"
    lens.save(update_fields=["status"])
    routine = lens.current_routine()
    assert routine.kind == "scheduled"
    assert routine.schedule_time == time(8, 0)

    def afternoon(_value=None):
        return djtz.make_aware(datetime(2026, 9, 14, 15, 0, 0))

    monkeypatch.setattr(tasks.timezone, "localtime", afternoon)
    assert _should_run(lens) is False


@respx.mock
@pytest.mark.django_db
def test_explanation_failure_still_persists_event_result(monkeypatch):
    user = User.objects.create_user(username="exp", email="exp@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, GOLDEN)
    dropped = json.loads(json.dumps(FIXTURE))
    dropped["data"][0]["quote"]["USD"]["percent_change_24h"] = -3.1
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest").mock(
        return_value=httpx.Response(200, json=_btc_drop_payload(-3.1))
    )
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json=dropped)
    )

    def boom(*args, **kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr("apps.lenses.runtime.explain_event", boom)
    run = LensRuntime(adapter=CMCAdapter(api_key="test-key")).trigger_routine(lens.id)
    assert run.status == "ok"
    from apps.events.models import Event

    event = Event.objects.get(lens=lens)
    assert "BTC" in event.explanation
    assert "hack" not in event.explanation.lower()
    assert Result.objects.filter(lens=lens, kind="ranked_table").exists()
    assert ConversationItem.objects.filter(lens=lens, item_type="event_result").exists()
