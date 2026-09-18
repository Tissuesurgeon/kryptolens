import json
from pathlib import Path

import httpx
import pytest
import respx
from django.test import Client

from apps.cmc.adapter import CMCAdapter
from apps.cmc.normalize import flatten_historical_quotes
from apps.lenses.agent_service import AgentService
from apps.lenses.models import Lens, LensRun, Result
from apps.lenses.runtime import LensRuntime
from apps.lenses.services import create_lens_from_intent
from apps.users.models import User

PASSWORD = "Workspace-secret-99"
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "listings_latest.json").read_text())
GOLDEN = "When BTC drops by 2%, check the top 100 coins and rank their declines."
GLOBAL = {
    "status": {"timestamp": "2026-09-16T00:00:00.000Z", "credit_count": 1},
    "data": {
        "btc_dominance": 57.8,
        "quote": {"USD": {"total_market_cap": 3920000000000}},
    },
}


def _user():
    return User.objects.create_user(username="ws", email="ws@kryptolens.app", password=PASSWORD)


def _client(user=None):
    client = Client()
    user = user or _user()
    client.force_login(user)
    return client, user


def _quotes_payload():
    data = {}
    for item in FIXTURE["data"]:
        data[item["symbol"]] = item
    data.setdefault(
        "ETH",
        {
            "id": 1027,
            "name": "Ethereum",
            "symbol": "ETH",
            "cmc_rank": 2,
            "quote": {"USD": {"price": 4012, "percent_change_24h": -0.84, "market_cap": 1}},
        },
    )
    return {"status": FIXTURE["status"], "data": data}


@pytest.mark.django_db
def test_create_agent_keeps_user_name():
    client, user = _client()
    response = client.post(
        "/agents/new",
        {"name": "Market Scout", "purpose": "Monitor crypto markets and investigate significant moves."},
        follow=True,
    )
    assert response.status_code == 200
    lens = Lens.objects.get(user=user)
    assert lens.name == "Market Scout"
    assert "Monitor crypto markets" in lens.purpose
    html = response.content.decode()
    assert "Hi. I" not in html
    assert "Market Scout" in html
    assert "What would you like me to watch?" not in html
    assert lens.conversation_items.count() == 0
    chat = client.post(
        f"/agents/{lens.id}",
        {"intent": GOLDEN},
        follow=True,
    )
    lens.refresh_from_db()
    assert lens.name == "Market Scout"


@pytest.mark.django_db
def test_agents_home_lists_named_agents():
    client, user = _client()
    create_lens_from_intent(user, GOLDEN)
    home = client.get("/agents")
    assert home.status_code == 200
    assert b"Your Lenses" in home.content
    assert Lens.objects.get(user=user).name.encode() in home.content
    assert b"agent-row" in home.content
    assert b"agent-list" in home.content
    assert b"agent-card" not in home.content
    assert b"agent-grid" not in home.content


@respx.mock
@pytest.mark.django_db
def test_market_strip_hits_adapter():
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest").mock(
        return_value=httpx.Response(200, json=_quotes_payload())
    )
    respx.get("https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest").mock(
        return_value=httpx.Response(200, json=GLOBAL)
    )
    client, _ = _client()
    response = client.get("/market/strip")
    assert response.status_code == 200
    assert b"Live" in response.content
    assert b"CMC" in response.content
    assert b"BTC" in response.content
    assert b"$104,821" not in response.content
    quotes = [call for call in respx.calls if "quotes/latest" in str(call.request.url)]
    assert quotes


@respx.mock
@pytest.mark.django_db
def test_routine_run_now_unmet_trigger_is_no_result():
    user = _user()
    lens, _, _ = create_lens_from_intent(user, GOLDEN)
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": FIXTURE["status"],
                "data": {"BTC": FIXTURE["data"][0]},
            },
        )
    )
    run = LensRuntime(adapter=CMCAdapter(api_key="test-key")).trigger_routine(lens.id)
    assert run.status == "ok"
    result = Result.objects.get(lens=lens)
    assert result.kind == "no_result"
    assert "Trigger condition not met" in result.payload_json["message"]
    assert result.payload_json["actual"] == 1.4
    assert run.cmc_calls.exists()


@respx.mock
def test_historical_quotes_and_listings_use_historical_endpoints():
    historical_quotes = {
        "status": {"credit_count": 1, "timestamp": "2026-09-15T00:00:00.000Z"},
        "data": {
            "BTC": {
                "id": 1,
                "name": "Bitcoin",
                "symbol": "BTC",
                "quotes": [
                    {
                        "timestamp": "2026-09-15T12:00:00.000Z",
                        "quote": {"USD": {"price": 64000, "percent_change_24h": -2.2, "market_cap": 1}},
                    }
                ],
            }
        },
    }
    respx.get("https://pro-api.coinmarketcap.com/v2/cryptocurrency/quotes/historical").mock(
        return_value=httpx.Response(200, json=historical_quotes)
    )
    respx.get("https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/historical").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    adapter = CMCAdapter(api_key="test-key", as_of="2026-09-15")
    quotes = adapter.get_quotes(["BTC"])
    listings = adapter.get_listings(limit=3)
    assert quotes.endpoint == "/v2/cryptocurrency/quotes/historical"
    assert listings.endpoint == "/v1/cryptocurrency/listings/historical"
    flat = flatten_historical_quotes(historical_quotes)
    assert flat["data"][0]["symbol"] == "BTC"
    assert "quotes/latest" not in str(respx.calls[0].request.url)


@respx.mock
@pytest.mark.django_db
def test_historical_run_records_historical_endpoints():
    user = _user()
    lens, _, _ = create_lens_from_intent(user, GOLDEN)
    respx.get("https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/historical").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    run = LensRuntime(adapter=CMCAdapter(api_key="test-key", as_of="2026-09-15")).run_now(lens.id)
    assert run.status == "ok"
    endpoints = list(run.cmc_calls.values_list("endpoint", flat=True))
    assert any("listings/historical" in item for item in endpoints)
    assert not any("listings/latest" in item for item in endpoints)


@pytest.mark.django_db
def test_job_detail_lists_cmc_calls():
    client, user = _client()
    lens, version, _ = create_lens_from_intent(user, GOLDEN)
    run = LensRun.objects.create(
        lens=lens,
        lens_version=version,
        trigger="manual",
        status="ok",
        stage="complete",
    )
    from apps.cmc.models import CmcCallLog

    CmcCallLog.objects.create(
        lens_run=run,
        endpoint="/v3/cryptocurrency/quotes/latest",
        status_code=200,
        elapsed_ms=318,
        response_excerpt='{"status": {"credit_count": 1}}',
    )
    page = client.get(f"/jobs/{run.id}")
    assert page.status_code == 200
    assert b"/v3/cryptocurrency/quotes/latest" in page.content
    assert b"318ms" in page.content
    assert b"complete" in page.content
    assert b"Historical test" not in page.content


@pytest.mark.django_db
def test_chat_later_message_applies_persistent_job():
    client, user = _client()
    client.post("/lenses/create", {"intent": GOLDEN}, follow=True)
    lens = Lens.objects.get(user=user)
    version = lens.current_version().version
    follow = client.post(
        f"/lenses/{lens.id}",
        {"intent": "When ETH drops 5%, investigate the top 100."},
        follow=True,
    )
    assert follow.status_code == 200
    lens.refresh_from_db()
    assert lens.current_version().version == version + 1
    assert b"You asked" in follow.content
    assert b"Create routine" not in follow.content
    assert b"Watching" in follow.content


def test_no_demo_mode_flag():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    forbidden = []
    for path in root.rglob("*.py"):
        if "test_" in path.name or "migrations" in str(path):
            continue
        text = path.read_text()
        if "demo_mode" in text:
            forbidden.append(str(path))
    assert forbidden == []


@pytest.mark.django_db
def test_empty_agents_home_only_create():
    client, _ = _client()
    home = client.get("/agents")
    assert home.status_code == 200
    assert b"Your Lenses" in home.content
    assert b"Create a Lens" in home.content
    assert b"agent-card" not in home.content
    assert b"+ New Lens" in home.content
    assert b"No Lenses yet" in home.content
    assert b"first-run" in home.content


@pytest.mark.django_db
def test_chat_first_message_attaches_job():
    client, user = _client()
    created = client.post("/agents/new", {"name": "Night Desk", "purpose": ""}, follow=True)
    assert created.status_code == 200
    lens = Lens.objects.get(user=user)
    assert lens.name == "Night Desk"
    assert lens.current_version() is None
    created_html = created.content.decode()
    assert "Hi. I" not in created_html
    assert "What would you like me to watch?" not in created_html
    assert "Night Desk" in created_html
    assert "Ask KryptoLens" in created_html
    assert lens.conversation_items.count() == 0
    chat = client.post(
        f"/agents/{lens.id}",
        {"intent": GOLDEN},
        follow=True,
    )
    assert chat.status_code == 200
    lens.refresh_from_db()
    assert lens.current_version() is not None
    assert lens.name == "Night Desk"
    assert b"You asked" in chat.content
    assert b"KryptoLens assumed" in chat.content
    assert b"WHEN" in chat.content
    assert b"DO" in chat.content
    assert b"DATA" in chat.content
    assert b"FAILURE" in chat.content
    assert b"Historical" not in chat.content
    assert b"Routine activated" in chat.content
    assert b"Create routine" not in chat.content
    assert b"Ask KryptoLens" in chat.content
    assert lens.status == "active"
    assert b"Watching" in chat.content


@pytest.mark.django_db
def test_home_with_agents_does_not_redirect():
    client, user = _client()
    create_lens_from_intent(user, GOLDEN)
    home = client.get("/home")
    assert home.status_code == 200
    assert b"agent-row" in home.content
    assert b"Your Lenses" in home.content
    assert b"Delete" in home.content
    assert b"agent-remove" in home.content


@pytest.mark.django_db
def test_user_can_delete_own_agent():
    client, user = _client()
    client.post("/agents/new", {"name": "Night Desk", "purpose": ""}, follow=True)
    lens = Lens.objects.get(user=user)
    denied_get = client.get(f"/agents/{lens.id}/delete")
    assert denied_get.status_code == 405
    deleted = client.post(f"/agents/{lens.id}/delete", follow=True)
    assert deleted.status_code == 200
    assert not Lens.objects.filter(pk=lens.id).exists()
    assert b"Deleted Night Desk" in deleted.content
    assert not Lens.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_cannot_delete_another_users_agent():
    client, _user_a = _client()
    other = User.objects.create_user(username="other", email="other@kryptolens.app", password=PASSWORD)
    lens = AgentService.create(other, "Secret", "")
    denied = client.post(f"/agents/{lens.id}/delete")
    assert denied.status_code == 404
    assert Lens.objects.filter(pk=lens.id).exists()


@pytest.mark.django_db
def test_delete_agent_removes_job_history():
    user = _user()
    lens, version, _ = create_lens_from_intent(user, GOLDEN)
    Result.objects.create(lens=lens, lens_version=version, kind="no_result", title="Quiet")
    AgentService.delete(lens)
    assert not Lens.objects.filter(pk=lens.id).exists()
    assert not Result.objects.filter(lens_id=lens.id).exists()
