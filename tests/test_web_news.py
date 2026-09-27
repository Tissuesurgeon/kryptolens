import json
from types import SimpleNamespace

import httpx
import pytest
import respx

from apps.cmc.adapter import CMCAdapter
from apps.intelligence.llm import HeuristicProvider
from apps.intelligence.response import compose_reply
from apps.intelligence.web_news import fetch_headlines, parse_headlines_html
from apps.intelligence.workflow import WorkflowDefinition, WorkflowStep
from apps.intelligence.workflow_executor import execute_steps

PAGE = """
<script id="__NEXT_DATA__" type="application/json">
{"props":{"pageProps":{"newsFeed":[
  {"slug":"sec","createdAt":"2026-09-26T10:28:00.000Z","meta":{"title":"SEC Commissioner Hester Peirce to Step Down","sourceName":"CoinDesk","sourceUrl":"https://coinmarketcap.com/community/en/articles/sec","releasedAt":"2026-09-26T10:28:00.000Z"}},
  {"slug":"sec-dup","meta":{"title":"SEC Commissioner Hester Peirce to Step Down","sourceUrl":"https://coinmarketcap.com/community/en/articles/sec","releasedAt":"2026-09-26T10:28:00.000Z"}},
  {"slug":"alphafi","meta":{"title":"Sui DeFi Protocol AlphaFi Winds Down","sourceName":"CoinCryptoNews","sourceUrl":"https://coinmarketcap.com/community/en/articles/alphafi","releasedAt":"2026-09-26T10:41:00.000Z"}},
  {"slug":"blank","meta":{"title":"","sourceUrl":"https://coinmarketcap.com/community/en/articles/blank"}}
]}}}
</script>
"""

QUOTES = {
    "status": {"error_code": "0"},
    "data": {
        "BTC": {
            "id": 1,
            "name": "Bitcoin",
            "symbol": "BTC",
            "cmc_rank": 1,
            "quote": {"USD": {"price": 115432.18, "percent_change_24h": -1.42}},
        }
    },
}


def test_parse_headlines_keeps_title_link_and_time():
    rows = parse_headlines_html(PAGE)
    assert rows == [
        {
            "title": "SEC Commissioner Hester Peirce to Step Down",
            "link": "https://coinmarketcap.com/community/en/articles/sec",
            "time": "2026-09-26T10:28:00.000Z",
            "source_name": "CoinDesk",
        },
        {
            "title": "Sui DeFi Protocol AlphaFi Winds Down",
            "link": "https://coinmarketcap.com/community/en/articles/alphafi",
            "time": "2026-09-26T10:41:00.000Z",
            "source_name": "CoinCryptoNews",
        },
    ]


def test_parse_empty_page_returns_no_headlines():
    assert parse_headlines_html("<html></html>") == []
    assert parse_headlines_html("") == []


def test_fetch_headlines_stays_offline_during_tests():
    assert fetch_headlines() == []


def test_relevance_keeps_only_titles_the_model_marked():
    headlines = [
        {
            "title": "SEC Commissioner Hester Peirce to Step Down",
            "link": "https://coinmarketcap.com/community/en/articles/sec",
            "time": "2026-09-26T10:28:00.000Z",
        },
        {
            "title": "Sui DeFi Protocol AlphaFi Winds Down",
            "link": "https://coinmarketcap.com/community/en/articles/alphafi",
            "time": "2026-09-26T10:41:00.000Z",
        },
    ]

    class Stub:
        def __init__(self):
            self.prompts = []

        def generate(self, prompt, kind=""):
            self.prompts.append(prompt)
            if kind == "relevance":
                return json.dumps(
                    {
                        "relevant": [
                            {
                                "title": "SEC Commissioner Hester Peirce to Step Down",
                                "reason": "The user asked about the SEC.",
                            },
                            {"title": "Invented headline", "reason": "not fetched"},
                        ]
                    }
                )
            return (
                "Bitcoin is at $115,432.18, down 1.42% over 24 hours. "
                "CoinMarketCap headline: SEC Commissioner Hester Peirce to Step Down. "
                "The user asked about the SEC."
            )

    result = SimpleNamespace(
        kind="comparison",
        title="Bitcoin",
        payload_json={
            "rows": [{"symbol": "BTC", "name": "Bitcoin", "price": 115432.18, "price_change_24h": -1.42}],
            "headlines": headlines,
        },
    )
    provider = Stub()
    text = compose_reply(
        result,
        provider=provider,
        task={"you_asked": ["any SEC news with bitcoin?"], "scope": {"assets": ["BTC"]}},
    )
    assert [item["title"] for item in result.payload_json["relevant_headlines"]] == [
        "SEC Commissioner Hester Peirce to Step Down"
    ]
    assert result.payload_json["relevant_headlines"][0]["reason"] == "The user asked about the SEC."
    assert "AlphaFi" not in provider.prompts[-1]
    assert "SEC Commissioner Hester Peirce to Step Down" in text


def test_relevance_failure_does_not_invent_a_match():
    class Stub:
        def generate(self, prompt, kind=""):
            if kind == "relevance":
                raise RuntimeError("model down")
            return "Bitcoin is at $115,432.18, down 1.42% over 24 hours."

    result = SimpleNamespace(
        kind="comparison",
        title="Bitcoin",
        payload_json={
            "rows": [{"symbol": "BTC", "name": "Bitcoin", "price": 115432.18, "price_change_24h": -1.42}],
            "headlines": [
                {
                    "title": "Sui DeFi Protocol AlphaFi Winds Down",
                    "link": "https://coinmarketcap.com/community/en/articles/alphafi",
                    "time": "2026-09-26T10:41:00.000Z",
                }
            ],
        },
    )
    text = compose_reply(
        result,
        provider=Stub(),
        task={"you_asked": ["how is bitcoin doing?"], "scope": {"assets": ["BTC"]}},
    )
    assert result.payload_json["headlines_judged"] is False
    assert result.payload_json["relevant_headlines"] == []
    assert "AlphaFi" not in text
    assert "115,432.18" in text


def test_heuristic_reply_stays_the_price_sentence():
    result = SimpleNamespace(
        kind="comparison",
        title="Bitcoin",
        payload_json={
            "rows": [{"symbol": "BTC", "name": "Bitcoin", "price": 115432.18, "price_change_24h": -1.42}],
            "headlines": [
                {
                    "title": "Sui DeFi Protocol AlphaFi Winds Down",
                    "link": "https://coinmarketcap.com/a",
                    "time": "2026-09-26T10:41:00.000Z",
                }
            ],
        },
    )
    text = compose_reply(result, provider=HeuristicProvider())
    assert "Bitcoin is at $115,432.18" in text
    assert "down 1.42%" in text
    assert "AlphaFi" not in text
    assert "relevant_headlines" not in result.payload_json


class _Run:
    def set_stage(self, stage):
        self.stage = stage


@respx.mock
def test_content_api_failure_uses_the_public_page(monkeypatch):
    monkeypatch.setattr("apps.intelligence.workflow_executor.persist_call", lambda call, run: None)
    monkeypatch.setattr(
        "apps.intelligence.workflow_executor.fetch_headlines",
        lambda: [
            {
                "title": "SEC Commissioner Hester Peirce to Step Down",
                "link": "https://coinmarketcap.com/community/en/articles/sec",
                "time": "2026-09-26T10:28:00.000Z",
                "source_name": "CoinDesk",
            }
        ],
    )
    respx.get("https://pro-api.coinmarketcap.com/v1/content/latest").mock(
        return_value=httpx.Response(403, json={"status": {"error_message": "plan"}})
    )
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest").mock(
        return_value=httpx.Response(200, json=QUOTES)
    )
    workflow = WorkflowDefinition(
        steps=[
            WorkflowStep(type="get_content", source="news", limit=5),
            WorkflowStep(type="get_quotes", symbols=["BTC"]),
            WorkflowStep(type="present", format="news_brief"),
        ]
    )
    built = execute_steps(CMCAdapter(api_key="test-key"), workflow, {}, _Run())
    assert built["kind"] == "news_brief"
    assert built["payload"]["headlines"][0]["title"] == "SEC Commissioner Hester Peirce to Step Down"


@respx.mock
def test_comparison_payload_keeps_fetched_headlines(monkeypatch):
    monkeypatch.setattr("apps.intelligence.workflow_executor.persist_call", lambda call, run: None)
    monkeypatch.setattr(
        "apps.intelligence.workflow_executor.fetch_headlines",
        lambda: [
            {
                "title": "Sui DeFi Protocol AlphaFi Winds Down",
                "link": "https://coinmarketcap.com/community/en/articles/alphafi",
                "time": "2026-09-26T10:41:00.000Z",
            }
        ],
    )
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/quotes/latest").mock(
        return_value=httpx.Response(200, json=QUOTES)
    )
    workflow = WorkflowDefinition(
        steps=[
            WorkflowStep(type="get_quotes", symbols=["BTC"]),
            WorkflowStep(type="present", format="comparison"),
        ]
    )
    built = execute_steps(CMCAdapter(api_key="test-key"), workflow, {}, _Run())
    assert built["kind"] == "comparison"
    assert built["payload"]["rows"][0]["price"] == 115432.18
    assert built["payload"]["headlines"][0]["link"].endswith("/alphafi")
