import json
from pathlib import Path

import httpx
import pytest
import respx
from django.test import Client

from apps.cmc.models import CmcCallLog
from apps.lenses.agent_service import AgentService
from apps.lenses.conversation import is_visible_thread_item
from apps.lenses.conversation_service import ConversationService
from apps.lenses.models import Lens, Result
from apps.lenses.routine_service import RoutineService
from apps.lenses.services import create_lens_from_intent
from apps.users.models import User

PASSWORD = "Workspace-secret-99"
GOLDEN = "When BTC drops by 2%, check the top 100 coins and rank their declines."
LISTINGS = json.loads((Path(__file__).parent / "fixtures" / "listings_latest.json").read_text())


def _user():
    return User.objects.create_user(username="facade", email="facade@kryptolens.app", password=PASSWORD)


@pytest.mark.django_db
def test_agent_service_keeps_user_name():
    user = _user()
    lens = AgentService.create(user, "Night Desk", "Monitor crypto markets and investigate significant moves.")
    assert lens.name == "Night Desk"
    assert lens.conversation_items.count() == 0
    assert ConversationService.command("check now") == "check"
    assert ConversationService.command("pause this") == "pause"


@pytest.mark.django_db
def test_list_for_user_includes_draft_without_purpose():
    user = _user()
    AgentService.create(user, "analyst", "")
    listed = AgentService.list_for_user(user)
    assert len(listed) == 1
    assert listed[0].name == "analyst"
    assert listed[0].agent_state["label"]
    assert listed[0].last_activity


@pytest.mark.django_db
def test_canned_opener_is_removed_from_existing_thread():
    from apps.lenses.conversation import add_item

    user = _user()
    lens = AgentService.create(user, "analyst", "monitoring the market activities")
    add_item(
        lens,
        "assistant_message",
        {"text": "Hi. I'm analyst. monitoring the market activities. What would you like me to watch?"},
    )
    assert lens.conversation_items.count() == 1
    ConversationService.context(lens)
    assert lens.conversation_items.count() == 0


@pytest.mark.django_db
def test_conversation_service_handle_without_http():
    user = _user()
    lens = AgentService.create(user, "Night Desk", "")
    result = ConversationService.handle(lens, GOLDEN)
    assert result.kind == "run"
    assert result.run is not None
    lens.refresh_from_db()
    assert lens.current_version() is not None
    assert lens.status == "active"
    assert lens.current_routine() is not None
    later = ConversationService.handle(lens, "When ETH drops 5%, investigate the top 100.")
    assert later.kind == "run"
    lens.refresh_from_db()
    assert lens.current_version().version == 2
    confirmed = ConversationService.handle(lens, GOLDEN, action="create_routine")
    assert confirmed.kind == "routine_created"


@pytest.mark.django_db
def test_status_question_runs_once_and_repeat_does_not_rewrite_the_job():
    user = _user()
    lens = AgentService.create(user, "analyst", "")
    text = "how is bitcoin doing on the market today"
    first = ConversationService.handle(lens, text)
    assert first.kind == "run"
    lens.refresh_from_db()
    version = lens.current_version()
    job = version.as_job()
    assert job.execution_model == "task"
    assert job.is_persistent() is False
    assert lens.status == "draft"
    assert lens.current_routine() is None
    assert not any(
        item.item_type == "routine_created" for item in lens.conversation_items.all()
    )
    asked = " ".join(
        (item.payload_json or {}).get("text") or ""
        for item in lens.conversation_items.filter(item_type="user_message")
    )
    assert "how is bitcoin doing on the market today" in asked
    assert not any(item.item_type == "job_created" for item in lens.conversation_items.all())
    later = ConversationService.handle(lens, text)
    assert later.kind == "run"
    lens.refresh_from_db()
    assert lens.current_version().version == version.version
    later.run.refresh_from_db()
    assert later.run.stage != "queued"


@respx.mock
@pytest.mark.django_db
def test_status_question_answers_with_live_btc_quote():
    payload = {
        "status": {"timestamp": "2026-09-17T15:17:26.927Z", "error_code": "0", "credit_count": 1},
        "data": [
            {
                "id": 1,
                "name": "Bitcoin",
                "symbol": "BTC",
                "cmc_rank": 1,
                "tags": [{"slug": "mineable", "name": "Mineable", "category": "OTHERS"}],
                "quote": [
                    {"symbol": "USD", "price": 115432.18, "percent_change_24h": -1.42, "market_cap": 2.2e12}
                ],
            }
        ],
    }
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest").mock(
        return_value=httpx.Response(200, json=payload)
    )
    user = _user()
    lens = AgentService.create(user, "analyst", "")
    ConversationService.handle(lens, "how is bitcoin doing on the market today")
    result = Result.objects.get(lens=lens)
    assert result.kind == "comparison"
    assert result.payload_json["rows"][0]["price"] == 115432.18
    types = list(lens.conversation_items.values_list("item_type", flat=True))
    assert "status_update" not in types
    assert "cmc_activity" not in types
    answer = lens.conversation_items.get(item_type="assistant_message")
    assert "Bitcoin is at $115,432.18" in answer.payload_json["text"]
    assert "down 1.42%" in answer.payload_json["text"]
    assert types.index("assistant_message") < types.index("scan_result")
    excerpt = CmcCallLog.objects.filter(endpoint__icontains="quotes").order_by("-id").first().response_excerpt
    assert "mineable" not in excerpt
    assert "115432.18" in excerpt
    client = Client()
    client.force_login(user)
    page = client.get(f"/lenses/{lens.id}")
    html = page.content
    assert b"Bitcoin is at $115,432.18" in html
    assert b"I understand the job" not in html
    assert b"I'll do" not in html
    assert b"Evidence" not in html
    assert b"Verification" not in html
    assert b"observed universe" not in html
    assert b"Evidence collected" not in html
    assert b"Market quotes" not in html
    assert b"View API data" not in html
    assert b'starter-label">Working' not in html
    visible = ConversationService.context(lens)["conversation_items"]
    assert all(is_visible_thread_item(item) for item in visible)
    assert [item.item_type for item in visible] == ["user_message", "assistant_message"]
    assert not any(item.item_type in {"cmc_activity", "status_update", "evidence", "verification", "job_created", "scan_result"} for item in visible)


def _quote_payload(symbol: str, name: str, price: float, change: float, asset_id: int):
    return {
        "status": {"timestamp": "2026-09-17T15:17:26.927Z", "error_code": "0", "credit_count": 1},
        "data": [
            {
                "id": asset_id,
                "name": name,
                "symbol": symbol,
                "cmc_rank": 1 if symbol == "BTC" else 2,
                "tags": [],
                "quote": [{"symbol": "USD", "price": price, "percent_change_24h": change, "market_cap": 1e11}],
            }
        ],
    }


@respx.mock
@pytest.mark.django_db
def test_eth_followup_quotes_eth_not_the_previous_btc_snapshot():
    def quotes(request):
        symbol = (request.url.params.get("symbol") or "").upper()
        if "ETH" in symbol:
            return httpx.Response(200, json=_quote_payload("ETH", "Ethereum", 2459.31, 2.50, 1027))
        return httpx.Response(200, json=_quote_payload("BTC", "Bitcoin", 77962.46, 1.73, 1))

    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest").mock(side_effect=quotes)
    user = _user()
    lens = AgentService.create(user, "analyst", "")
    ConversationService.handle(lens, "what is btc doing right now")
    later = ConversationService.handle(lens, "what is ETH doing right now")
    assert later.kind == "run"
    answers = list(lens.conversation_items.filter(item_type="assistant_message"))
    assert "Ethereum is at $2,459.31" in answers[-1].payload_json["text"]
    assert "up 2.50%" in answers[-1].payload_json["text"]
    result = Result.objects.filter(lens=lens).order_by("-id").first()
    assert result.payload_json["rows"][0]["symbol"] == "ETH"


@respx.mock
@pytest.mark.django_db
def test_highest_gains_ranks_listings_instead_of_quoting_btc():
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json=LISTINGS)
    )
    user = _user()
    lens = AgentService.create(user, "analyst", "")
    later = ConversationService.handle(lens, "find me the coins with the highest gains within 24hrs")
    assert later.kind == "run"
    lens.refresh_from_db()
    assert lens.current_routine() is None
    result = Result.objects.filter(lens=lens).order_by("-id").first()
    assert result.kind == "ranked_table"
    assert result.payload_json["rows"][0]["symbol"] == "SOL"
    assert result.payload_json["rows"][0]["price_change_24h"] == 12.4
    answer = list(lens.conversation_items.filter(item_type="assistant_message"))[-1]
    assert "Highest 24h gains" in answer.payload_json["text"]
    assert "Solana" in answer.payload_json["text"]
    assert "up 12.40%" in answer.payload_json["text"]
    assert not any(item.item_type == "job_created" for item in lens.conversation_items.all())
    client = Client()
    client.force_login(user)
    html = client.get(f"/lenses/{lens.id}").content
    assert b"I understand the job" not in html
    assert b"I'll do" not in html
    assert b"Solana" in html
    visible = ConversationService.context(lens)["conversation_items"]
    assert not any(item.item_type in {"evidence", "verification", "job_created"} for item in visible)
    assert any(item.item_type == "scan_result" for item in visible)


@respx.mock
@pytest.mark.django_db
def test_btc_drop_highest_drop_ranks_declines_not_prior_gains():
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json=LISTINGS)
    )
    user = _user()
    lens = AgentService.create(user, "analyst", "")
    ConversationService.handle(lens, "find me the coins with the highest gains within 24hrs")
    later = ConversationService.handle(lens, "when btc drops by 2%, find me the coins with the highest drop")
    assert later.kind == "run"
    lens.refresh_from_db()
    workflow = lens.current_version().as_workflow()
    assert workflow.trigger.asset == "BTC"
    assert workflow.trigger.value == -2.0
    assert any(step.type == "sort" and step.order == "ascending" for step in workflow.steps)
    assert not any(step.type == "filter" and step.operator == ">" for step in workflow.steps)
    types = list(lens.conversation_items.values_list("item_type", flat=True))
    assert "policy_diff" not in types
    assert "workflow_created" in types
    result = Result.objects.filter(lens=lens).order_by("-id").first()
    assert result.kind == "ranked_table"
    changes = [row["price_change_24h"] for row in result.payload_json["rows"]]
    assert changes == sorted(changes)


@pytest.mark.django_db
def test_chat_run_finishes_without_celery_worker(monkeypatch):
    monkeypatch.setattr("apps.lenses.run_service.run_lens_task.delay", lambda *args, **kwargs: None)
    user = _user()
    lens = AgentService.create(user, "analyst", "")
    result = ConversationService.handle(lens, "how is bitcoin doing on the market today")
    assert result.kind == "run"
    result.run.refresh_from_db()
    assert result.run.stage != "queued"


@pytest.mark.django_db
def test_status_question_does_not_show_job_update_after_a_watch():
    user = _user()
    lens = AgentService.create(user, "analyst", "")
    ConversationService.handle(lens, GOLDEN)
    lens.refresh_from_db()
    assert lens.current_version().as_job().is_persistent() is True
    later = ConversationService.handle(lens, "how is bitcoin doing on the market today")
    assert later.kind == "run"
    lens.refresh_from_db()
    standing = lens.current_version().as_job()
    assert standing.is_persistent() is True
    assert standing.execution_model == "watch_plus_workflow"
    assert not any(item.item_type == "policy_diff" for item in lens.conversation_items.all())
    asked = " ".join(item.payload_json.get("text") or "" for item in lens.conversation_items.filter(item_type="user_message"))
    assert "how is bitcoin doing on the market today" in asked


@pytest.mark.django_db
def test_eth_ask_does_not_replace_standing_btc_watch():
    user = _user()
    lens = AgentService.create(user, "analyst", "")
    ConversationService.handle(lens, GOLDEN)
    lens.refresh_from_db()
    version = lens.current_version().version
    ConversationService.handle(lens, "what is ETH doing right now")
    lens.refresh_from_db()
    standing = lens.current_version().as_job()
    assert lens.current_version().version == version
    assert standing.is_persistent() is True
    assert standing.execution_model == "watch_plus_workflow"


@pytest.mark.django_db
def test_news_is_not_a_chat_command():
    assert ConversationService.command("what news is affecting the crypto market today?") is None
    assert ConversationService.command("check now") == "check"


@pytest.mark.django_db
def test_routine_service_should_run_matches_beat():
    user = _user()
    lens, _, _ = create_lens_from_intent(user, GOLDEN)
    lens.status = "active"
    lens.save(update_fields=["status"])
    assert RoutineService.should_run(lens)
    routine = lens.current_routine()
    routine.paused = True
    routine.save(update_fields=["paused"])
    assert not RoutineService.should_run(lens)


@pytest.mark.django_db
def test_web_chat_still_uses_conversation_service():
    client = Client()
    user = _user()
    client.force_login(user)
    created = client.post("/agents/new", {"name": "Night Desk", "purpose": ""}, follow=True)
    assert created.status_code == 200
    lens = Lens.objects.get(user=user)
    follow = client.post(f"/agents/{lens.id}", {"intent": GOLDEN}, follow=True)
    assert follow.status_code == 200
    lens.refresh_from_db()
    assert lens.current_version() is not None
    assert b"You asked" in follow.content
    assert b"Routine activated" in follow.content
    assert b"Create routine" not in follow.content
    lens.refresh_from_db()
    assert lens.status == "active"


@pytest.mark.django_db
def test_telegram_inbound_writes_the_same_conversation():
    from apps.lenses.models import ConversationItem
    from apps.notifications.telegram_service import TelegramService
    from apps.users.models import UserPreference

    user = _user()
    lens = AgentService.create(user, "Market Scout", "Watch the market.")
    UserPreference.objects.update_or_create(
        user=user,
        defaults={"telegram_chat_id": "4242", "telegram_enabled": True, "active_lens": lens},
    )
    sent = []
    result = TelegramService.handle_update(
        {"message": {"chat": {"id": 4242}, "text": GOLDEN}},
        sender=lambda chat_id, text: sent.append((chat_id, text)),
        public_base="http://example.test",
    )
    assert result["ok"] is True
    assert ConversationItem.objects.filter(lens=lens, item_type="routine_created").exists()
    assert ConversationItem.objects.filter(lens=lens, item_type="user_message").exists()
    assert not ConversationItem.objects.filter(lens=lens, item_type="routine_proposal").exists()
    assert any("Routine activated" in text or "is working" in text or "Run queued" in text for _, text in sent)
    assert not any("drafted a routine" in text for _, text in sent)
    assert any(str(chat) == "4242" for chat, _ in sent)


@pytest.mark.django_db
def test_telegram_webhook_rejects_bad_secret(settings):
    settings.TELEGRAM_WEBHOOK_SECRET = "s3cret"
    client = Client()
    denied = client.post("/telegram/webhook/nope", data="{}", content_type="application/json")
    assert denied.status_code == 403
    ok = client.post(
        "/telegram/webhook/s3cret",
        data="{}",
        content_type="application/json",
    )
    assert ok.status_code == 200


@pytest.mark.django_db
def test_pause_resume_check_now_are_state_messages():
    user = _user()
    lens = AgentService.create(user, "Scout", "")
    ConversationService.handle(lens, GOLDEN)
    paused = ConversationService.handle(lens, "pause")
    assert paused.flash == "Routine paused."
    resumed = ConversationService.handle(lens, "resume")
    assert resumed.flash == "Routine activated."
    check = ConversationService.handle(lens, "check now")
    assert check.flash == "Run queued."
    evidence = ConversationService.handle(lens, "show evidence")
    assert evidence.kind == "replied"


@pytest.mark.django_db
def test_eth_reaction_creates_persistent_routine():
    user = _user()
    lens = AgentService.create(user, "Crypto Scout", "")
    result = ConversationService.handle(
        lens,
        "When ETH drops by 2%, check the top 100 coins and rank their declines from biggest to smallest.",
    )
    assert result.kind == "run"
    lens.refresh_from_db()
    job = lens.current_version().as_job()
    workflow = lens.current_version().as_workflow()
    assert job.is_persistent() is True
    assert workflow.trigger.asset == "ETH"
    assert lens.current_routine() is not None


@pytest.mark.django_db
def test_unusual_watch_asks_before_queuing():
    user = _user()
    lens = AgentService.create(user, "Crypto Scout", "")
    result = ConversationService.handle(lens, "Watch BTC and tell me when something important happens.")
    assert result.kind == "needs_input"
    assert result.run is None
    assert lens.current_version() is None
    question = lens.conversation_items.get(item_type="assistant_message")
    assert "significant" in question.payload_json["text"].lower() or "price" in question.payload_json["text"].lower()
    later = ConversationService.handle(lens, "a 3% drop")
    assert later.kind == "run"
    lens.refresh_from_db()
    assert lens.current_version().as_job().is_persistent() is True
    assert lens.current_routine() is not None


@pytest.mark.django_db
def test_execution_trace_only_includes_persisted_stages():
    from apps.lenses.models import LensRun
    from apps.lenses.run_service import RunService

    user = _user()
    lens, version, _ = create_lens_from_intent(user, GOLDEN)
    run = LensRun.objects.create(
        lens=lens,
        lens_version=version,
        trigger="routine",
        status="running",
        stage="evaluating",
    )
    trace = RunService.get_trace(run)
    ids = [step["id"] for step in trace["stages"]]
    assert ids[-1] == "evaluating"
    assert trace["stages"][-1]["current"] is True
    assert "complete" not in ids
    assert "notifying" not in ids
