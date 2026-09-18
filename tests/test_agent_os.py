import json
from pathlib import Path

import httpx
import pytest
import respx

from apps.cmc.adapter import CMCAdapter
from apps.intelligence.agent import AgentPlan, ChiefAgent, PlanValidationError, validate_agent_plan
from apps.intelligence.agent_runtime import AgentRuntime
from apps.intelligence.permissions import EXECUTE, READ, require_sensitivity
from apps.intelligence.tools import ToolPermissionError
from apps.intelligence.verification import claim_supported, verify_result
from apps.lenses.models import (
    AgentTask,
    ApprovalRequest,
    Artifact,
    Evidence,
    Job,
    Result,
    VerificationRecord,
)
from apps.lenses.services import apply_intent_edit, create_lens_from_intent
from apps.users.models import User

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "listings_latest.json").read_text())
GOLDEN = "When BTC drops by 2%, check the top 100 coins and rank their declines."


@pytest.mark.django_db
def test_signup_rejects_duplicate_email():
    from django.test import Client

    User.objects.create_user(username="dup", email="dup@kryptolens.app", password="Workspace-secret-99")
    client = Client()
    response = client.post(
        "/signup",
        {
            "email": "dup@kryptolens.app",
            "password": "Workspace-secret-99",
            "password_confirm": "Workspace-secret-99",
        },
    )
    assert response.status_code == 200
    assert User.objects.filter(email="dup@kryptolens.app").count() == 1
    assert b"already exists" in response.content


@pytest.mark.django_db
def test_signup_rejects_weak_password():
    from django.test import Client

    client = Client()
    response = client.post(
        "/signup",
        {
            "email": "weak@kryptolens.app",
            "password": "123",
            "password_confirm": "123",
        },
    )
    assert response.status_code == 200
    assert not User.objects.filter(email="weak@kryptolens.app").exists()
    assert b"password" in response.content.lower()


@pytest.mark.django_db
def test_job_and_snapshot_both_persist():
    user = User.objects.create_user(username="job", email="job@kryptolens.app", password="x")
    lens, version, _ = create_lens_from_intent(user, GOLDEN)
    job = Job.objects.get(lens=lens)
    assert job.category == "investigate"
    assert job.objective
    assert version.job_definition_json["execution_model"] == "watch_plus_workflow"
    assert version.job_definition_json["purpose"]


@pytest.mark.django_db
def test_artifact_job_isolation():
    owner = User.objects.create_user(username="own", email="own@kryptolens.app", password="x")
    other = User.objects.create_user(username="oth", email="oth@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(owner, GOLDEN)
    assert Job.objects.filter(lens__user=other).count() == 0
    assert Artifact.objects.filter(lens__user=other).count() == 0
    assert Evidence.objects.filter(lens__user=other).count() == 0
    assert AgentTask.objects.filter(lens__user=other).count() == 0
    assert Job.objects.filter(lens=lens, lens__user=owner).exists()
    assert Artifact.objects.filter(lens=lens, kind="plan").exists()


def test_agent_plan_rejects_unknown_tool_and_code_step():
    with pytest.raises(ValueError):
        AgentPlan(
            plan_id="x",
            objective="hack",
            job_type="investigate",
            specialist="market",
            steps=["eval"],
            tools=["get_quotes"],
        )
    plan = AgentPlan(
        plan_id="x",
        objective="hack",
        job_type="investigate",
        specialist="market",
        steps=["check_btc"],
        tools=["os.system"],
    )
    with pytest.raises(PlanValidationError):
        validate_agent_plan(plan, {"get_quotes": True})


def test_chief_plan_from_clarified_task():
    from apps.intelligence.clarified_task import ClarifiedTask, TaskScope
    from apps.intelligence.task_compiler import compile_from_task

    task = ClarifiedTask(
        mode="ask",
        task_type="one_shot_research",
        objective="Report how BTC is doing",
        scope=TaskScope(assets=["BTC"]),
        capabilities=["market"],
        source_text="How is BTC doing?",
        you_asked=["How is BTC doing?"],
    )
    report = compile_from_task(task)
    plan = ChiefAgent().plan_from_task(task, report)
    assert "market" in plan.capabilities
    assert "get_quotes" in plan.tools
    assert plan.persistent is False


def test_chief_plan_does_not_call_cmc(monkeypatch):
    called = {"cmc": False}

    def boom(*args, **kwargs):
        called["cmc"] = True
        raise AssertionError("ChiefAgent must not call CMC")

    monkeypatch.setattr("apps.intelligence.tools.dispatch_cmc", boom)
    plan, report = ChiefAgent().plan_from_text(GOLDEN)
    assert called["cmc"] is False
    assert plan.job_type == "investigate"
    assert "get_quotes" in plan.tools
    assert "get_market_listings" in plan.tools
    assert report["workflow"].steps


def test_chief_plan_honors_top_20():
    plan, report = ChiefAgent().plan_from_text(
        "when bitcoin drops by 2%, check the top 20 coins and rank their declines"
    )
    assert "load_top_20" in plan.steps
    assert "load_top_100" not in plan.steps
    assert report["policy"].universe.limit == 20


def test_read_allowed_execute_denied():
    assert require_sensitivity("get_quotes") == READ
    with pytest.raises(ToolPermissionError, match="not available yet"):
        require_sensitivity(EXECUTE)


@pytest.mark.django_db
def test_approval_read_not_required_execute_denied():
    user = User.objects.create_user(username="appr", email="appr@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, GOLDEN)
    approval = ApprovalRequest.objects.get(lens=lens)
    assert approval.status == "not_required"
    assert approval.sensitivity == "READ"
    denied = ApprovalRequest.objects.create(
        lens=lens,
        user=user,
        action="execute_trade",
        sensitivity=EXECUTE,
        status="denied",
    )
    assert denied.status == "denied"
    with pytest.raises(ToolPermissionError):
        require_sensitivity("PREPARE")


@respx.mock
@pytest.mark.django_db
def test_agent_runtime_golden_btc_os_path():
    user = User.objects.create_user(username="os", email="os@kryptolens.app", password="x")
    lens, version, _ = create_lens_from_intent(user, GOLDEN)
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    run = AgentRuntime(adapter=CMCAdapter(api_key="test-key")).run_now(lens.id)
    assert run.status == "ok"
    result = Result.objects.filter(lens=lens, kind="ranked_table").first()
    assert result
    job = Job.objects.get(lens=lens)
    assert job.category == "investigate"
    assert version.job_definition_json
    assert AgentTask.objects.filter(lens=lens, assigned_agent="chief").exists()
    assert AgentTask.objects.filter(lens=lens, assigned_agent="market").exists()
    evidence = list(Evidence.objects.filter(lens=lens, lens_run=run))
    assert evidence
    assert any(item.observation_ids for item in evidence)
    assert any(item.tool == "get_market_listings" for item in evidence)
    verification = VerificationRecord.objects.get(lens=lens, lens_run=run)
    labels = " ".join(check.get("label", "") for check in verification.checks_json)
    assert "Trigger verified" in labels
    assert "Ranking verified" in labels
    assert Artifact.objects.filter(lens=lens, lens_run=run, kind="plan").exists()
    assert Artifact.objects.filter(lens=lens, lens_run=run, kind="execution_receipt").exists()
    assert lens.conversation_items.filter(item_type="plan").exists()
    types = list(lens.conversation_items.filter(lens_run=run).values_list("item_type", flat=True))
    assert "assistant_message" in types
    assert "evidence" in types
    assert "cmc_activity" not in types
    assert types.index("assistant_message") < types.index("scan_result")
    assert types.index("scan_result") < types.index("evidence")
    assert types.index("evidence") < types.index("verification")
    assert types.index("verification") < types.index("execution_receipt")


@respx.mock
@pytest.mark.django_db
def test_insufficient_evidence_is_not_error():
    user = User.objects.create_user(username="empty", email="empty@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, GOLDEN)
    empty = {"status": {"error_code": 0}, "data": []}
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json=empty)
    )
    run = AgentRuntime(adapter=CMCAdapter(api_key="test-key")).run_now(lens.id)
    assert run.status == "ok"
    result = Result.objects.filter(lens=lens).order_by("-id").first()
    assert result.kind != "error"
    verification = verify_result(result, lens.current_version().as_workflow(), ChiefAgent().plan_from_version(lens.current_version()))
    assert verification["status"] in {"needs_more_evidence", "unsupported", "inconclusive", "supported"}


@respx.mock
@pytest.mark.django_db
def test_repair_retries_once(monkeypatch):
    user = User.objects.create_user(username="rep", email="rep@kryptolens.app", password="x")
    lens, _, _ = create_lens_from_intent(user, GOLDEN)
    calls = {"n": 0}

    def fake_execute(self, lens_id, trigger, run, honor_trigger, record_conversation=True):
        from apps.lenses.models import Lens, LensRun, Result

        calls["n"] += 1
        lens = Lens.objects.get(pk=lens_id)
        version = lens.current_version()
        if run is None:
            run = LensRun.objects.create(lens=lens, lens_version=version, trigger=trigger, status="ok", stage="complete")
        if calls["n"] == 1:
            Result.objects.create(
                lens=lens,
                lens_version=version,
                lens_run=run,
                kind="ranked_table",
                title="empty",
                payload_json={"rows": [], "assets": 0},
            )
            run.status = "ok"
            run.stage = "complete"
            run.save()
            return run
        Result.objects.create(
            lens=lens,
            lens_version=version,
            lens_run=run,
            kind="ranked_table",
            title="Market reaction",
            payload_json={
                "rows": [{"symbol": "ETH", "asset_id": 2, "price_change_24h": -3.0, "rank": 1}],
                "assets": 1,
                "trigger": {"asset": "BTC", "actual": -2.4, "threshold": -2, "fired": True},
            },
        )
        run.status = "ok"
        run.stage = "complete"
        run.save()
        return run

    monkeypatch.setattr("apps.lenses.runtime.LensRuntime._execute", fake_execute)
    run = AgentRuntime(adapter=CMCAdapter(api_key="test-key")).run_now(lens.id)
    assert calls["n"] == 2
    assert run.status == "ok"
    assert Result.objects.filter(lens=lens, title="Market reaction").exists()


@pytest.mark.django_db
def test_unsupported_claim_status():
    user = User.objects.create_user(username="claim", email="claim@kryptolens.app", password="x")
    lens, version, _ = create_lens_from_intent(user, GOLDEN)
    result = Result.objects.create(
        lens=lens,
        lens_version=version,
        kind="ranked_table",
        title="Market reaction",
        payload_json={"rows": [{"symbol": "ETH", "price_change_24h": -1}]},
    )
    assert claim_supported("SOL led the market", result, ["obs:1:ETH"]) == "unsupported"
    assert claim_supported("ETH declined", result, ["obs:1:ETH"]) == "supported"


@pytest.mark.django_db
def test_edit_updates_live_job_and_pins_old_version():
    user = User.objects.create_user(username="ed2", email="ed2@kryptolens.app", password="x")
    lens, v1, _ = create_lens_from_intent(user, GOLDEN)
    job = Job.objects.get(lens=lens)
    old_objective = job.objective
    old_plan = Artifact.objects.filter(lens=lens, kind="plan", lens_version=v1).first()
    version, _ = apply_intent_edit(
        lens, "Instead of top 100, use top 50 and only include assets that dropped more than BTC."
    )
    job.refresh_from_db()
    assert version.version == 2
    assert version.job_definition_json
    assert job.lens_version_id == version.id
    assert Artifact.objects.filter(lens=lens, kind="plan", lens_version=version).exists()
    assert old_plan.lens_version_id == v1.id
    assert job.objective


@pytest.mark.django_db
def test_morning_brief_is_research_job():
    user = User.objects.create_user(username="brief", email="brief@kryptolens.app", password="x")
    lens, version, _ = create_lens_from_intent(user, "Every morning summarize major crypto changes")
    job = Job.objects.get(lens=lens)
    assert job.category == "research"
    assert version.as_job().execution_model == "scheduled"
    assert lens.routines.filter(kind="scheduled").exists()
