import json
from pathlib import Path

import httpx
import pytest
import respx
from django.test import Client

from apps.cmc.adapter import CMCAdapter, CMCError
from apps.cmc.normalize import normalize_content
from apps.intelligence.news import heuristic_analysis, symbols_from_items
from apps.intelligence.observations import MarketObservation
from apps.lenses.agent_service import AgentService
from apps.lenses.conversation_service import ConversationService
from apps.lenses.models import Result
from apps.lenses.runtime import LensRuntime
from apps.lenses.services import create_lens_from_intent
from apps.users.models import User

CONTENT = json.loads((Path(__file__).parent / "fixtures" / "content_latest.json").read_text())
PASSWORD = "Workspace-secret-99"

QUOTES = {
    "status": {"timestamp": "2026-09-17T18:00:00.000Z", "error_code": "0", "credit_count": 1},
    "data": [
        {
            "id": 1,
            "name": "Bitcoin",
            "symbol": "BTC",
            "cmc_rank": 1,
            "quote": [{"symbol": "USD", "price": 76665.95, "percent_change_24h": 1.12, "market_cap": 1.5e12}],
        },
        {
            "id": 1027,
            "name": "Ethereum",
            "symbol": "ETH",
            "cmc_rank": 2,
            "quote": [{"symbol": "USD", "price": 2459.31, "percent_change_24h": 2.50, "market_cap": 3.0e11}],
        },
    ],
}


def _mock_news_cmc():
    respx.get("https://pro-api.coinmarketcap.com/v1/content/latest").mock(
        return_value=httpx.Response(200, json=CONTENT)
    )
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest").mock(
        return_value=httpx.Response(200, json=QUOTES)
    )


def test_normalize_content_latest():
    items = normalize_content(CONTENT)
    assert [item["title"] for item in items] == [
        "Bitcoin holds near session highs as ETF inflows continue",
        "Ethereum staking queue shortens",
    ]
    assert symbols_from_items(items) == ["BTC", "ETH"]


def test_heuristic_analysis_uses_quotes_not_causes():
    items = normalize_content(CONTENT)
    observations = [
        MarketObservation(asset_id=1, symbol="BTC", name="Bitcoin", price=76665.95, price_change_24h=1.12),
        MarketObservation(asset_id=1027, symbol="ETH", name="Ethereum", price=2459.31, price_change_24h=2.50),
    ]
    from apps.intelligence.news import attach_quotes

    text = heuristic_analysis(attach_quotes(items, observations), observations)
    assert "Bitcoin holds near session highs as ETF inflows continue" in text
    assert "$76,665.95" in text
    assert "caused" not in text.lower()


@respx.mock
def test_content_latest_forbidden_is_honest():
    respx.get("https://pro-api.coinmarketcap.com/v1/content/latest").mock(
        return_value=httpx.Response(403, json={"status": {"error_message": "plan"}})
    )
    adapter = CMCAdapter(api_key="test-key")
    with pytest.raises(CMCError, match="News/Headlines"):
        adapter.get_content_latest(limit=5)


@respx.mock
@pytest.mark.django_db
def test_news_question_relates_headlines_to_quotes():
    _mock_news_cmc()
    user = User.objects.create_user(username="news", email="news@kryptolens.app", password=PASSWORD)
    lens, _, _ = create_lens_from_intent(user, "what news is affecting the crypto market today?")
    run = LensRuntime(adapter=CMCAdapter(api_key="test-key")).run_now(lens.id)
    assert run.status == "ok"
    result = Result.objects.get(lens=lens)
    assert result.kind == "news_brief"
    assert result.payload_json["headlines"] == 2
    assert "Bitcoin holds near session highs as ETF inflows continue" in result.payload_json["analysis"]
    assert any(row["symbol"] == "BTC" and row["price"] == 76665.95 for row in result.payload_json["rows"])


@respx.mock
@pytest.mark.django_db
def test_news_chat_does_not_show_version_diff():
    _mock_news_cmc()
    user = User.objects.create_user(username="desk", email="desk@kryptolens.app", password=PASSWORD)
    lens = AgentService.create(user, "analyst", "")
    later = ConversationService.handle(lens, "what news is affecting the crypto market today?")
    assert later.kind == "run"
    lens.refresh_from_db()
    job = lens.current_version().as_job()
    assert job.execution_model == "task"
    assert job.news_unavailable is False
    assert not any(item.item_type == "policy_diff" for item in lens.conversation_items.all())
    result = Result.objects.get(lens=lens)
    assert result.kind == "news_brief"
    client = Client()
    client.force_login(user)
    html = client.get(f"/lenses/{lens.id}").content
    assert b"Bitcoin holds near session highs" in html
    assert b"update the job" not in html
    assert b"News monitoring isn" not in html
    spoken = lens.conversation_items.filter(item_type="assistant_message").order_by("-id").first()
    assert spoken is not None
    assert "ETF inflows" in spoken.payload_json["text"]
