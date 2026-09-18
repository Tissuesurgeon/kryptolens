import json
from pathlib import Path

import httpx
import pytest
import respx

from apps.cmc.adapter import CMCAdapter, CMCError
from apps.cmc.logging import _excerpt
from apps.cmc.normalize import is_stablecoin, normalize_fear_greed, normalize_listings, index_by_symbol, select_quoted_assets
from apps.intelligence.present import spoken_result

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "listings_latest.json").read_text())
FEAR = json.loads((Path(__file__).parent / "fixtures" / "fear_greed.json").read_text())


def test_normalize_listings_and_stablecoins():
    observations = normalize_listings(FIXTURE, previous_ranks={5426: 8})
    assert len(observations) == 3
    sol = next(item for item in observations if item.symbol == "SOL")
    assert sol.price_change_24h == 12.4
    assert sol.volume_change_24h == 210.5
    assert sol.rank_improved is True
    usdt = next(item for item in observations if item.symbol == "USDT")
    assert is_stablecoin(usdt) is True


def test_normalize_listings_v3_quote_array():
    payload = {
        "data": [
            {
                "id": 5426,
                "name": "Solana",
                "symbol": "SOL",
                "cmc_rank": 5,
                "quote": [
                    {
                        "symbol": "USD",
                        "price": 180.12,
                        "volume_24h": 6200000000,
                        "volume_change_24h": 210.5,
                        "percent_change_24h": 12.4,
                        "market_cap": 82000000000,
                    }
                ],
            }
        ]
    }
    observations = normalize_listings(payload, previous_ranks={5426: 8})
    sol = observations[0]
    assert sol.price_change_24h == 12.4
    assert sol.volume_change_24h == 210.5
    assert sol.rank_improved is True


def test_normalize_listings_v3_symbol_lists():
    payload = {
        "data": {
            "BTC": [
                {
                    "id": 1,
                    "name": "Bitcoin",
                    "symbol": "BTC",
                    "cmc_rank": 1,
                    "quote": [
                        {"symbol": "USD", "price": 64000, "percent_change_24h": 1.4}
                    ],
                }
            ],
            "SOL": [
                {
                    "id": 5426,
                    "name": "Solana",
                    "symbol": "SOL",
                    "cmc_rank": 5,
                    "quote": [
                        {"symbol": "USD", "price": 180.12, "percent_change_24h": 12.4}
                    ],
                }
            ],
        }
    }
    observations = {item.symbol: item for item in normalize_listings(payload)}
    assert observations["BTC"].price == 64000
    assert observations["SOL"].price == 180.12
    assert observations["BTC"].price_change_24h == 1.4


def test_index_by_symbol_keeps_canonical_listing():
    payload = {
        "data": [
            {
                "id": 1,
                "name": "Bitcoin",
                "symbol": "BTC",
                "cmc_rank": 1,
                "quote": {"USD": {"price": 75876, "percent_change_24h": 1.18, "market_cap": 1.5e12}},
            },
            {
                "id": 999001,
                "name": "Bitcoin Gold AI",
                "symbol": "BTC",
                "cmc_rank": 4821,
                "quote": {"USD": {"price": 0.0002, "percent_change_24h": 23.12, "market_cap": 1000}},
            },
            {
                "id": 5426,
                "name": "Solana",
                "symbol": "SOL",
                "cmc_rank": 5,
                "quote": {"USD": {"price": 180.12, "percent_change_24h": 1.4, "market_cap": 8.2e10}},
            },
            {
                "id": 999002,
                "name": "Solcoin",
                "symbol": "SOL",
                "cmc_rank": 8800,
                "quote": {"USD": {"price": None, "percent_change_24h": 0}},
            },
        ]
    }
    chosen = index_by_symbol(normalize_listings(payload))
    assert chosen["BTC"].name == "Bitcoin"
    assert chosen["BTC"].price == 75876
    assert chosen["SOL"].name == "Solana"
    assert chosen["SOL"].price == 180.12
    selected = select_quoted_assets(payload, ["BTC"])
    assert len(selected) == 1
    assert selected[0].name == "Bitcoin"
    assert selected[0].price == 75876


def test_quotes_excerpt_omits_tags_and_keeps_price():
    payload = {
        "status": {"timestamp": "2026-09-17T15:17:26.927Z", "error_code": "0", "credit_count": 1},
        "data": [
            {
                "id": 1,
                "name": "Bitcoin",
                "symbol": "BTC",
                "tags": [{"slug": "mineable", "name": "Mineable", "category": "OTHERS"}],
                "quote": [{"symbol": "USD", "price": 115432.18, "percent_change_24h": -1.42}],
            }
        ],
    }
    excerpt = _excerpt(payload)
    assert "mineable" not in excerpt
    assert "tags" not in excerpt
    assert "115432.18" in excerpt
    assert "-1.42" in excerpt


def test_spoken_comparison_states_price_and_24h_move():
    class Result:
        kind = "comparison"
        payload_json = {
            "rows": [
                {"name": "Bitcoin", "symbol": "BTC", "price": 115432.18, "price_change_24h": -1.42}
            ]
        }

    text = spoken_result(Result())
    assert "Bitcoin is at $115,432.18" in text
    assert "down 1.42% over 24 hours" in text


def test_normalize_fear_greed():
    context = normalize_fear_greed(FEAR)
    assert context.fear_greed_value == 74
    assert context.fear_greed_label == "Greed"


@respx.mock
def test_adapter_listings_success():
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    adapter = CMCAdapter(api_key="test-key")
    call = adapter.get_listings(limit=3)
    assert call.status_code == 200
    assert call.credit_count == 1
    assert "price" in call.fields_used
    assert "X-CMC_PRO_API_KEY" not in json.dumps(call.params)


@respx.mock
def test_adapter_timeout():
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        side_effect=httpx.TimeoutException("timeout")
    )
    adapter = CMCAdapter(api_key="test-key")
    with pytest.raises(CMCError, match="timed out"):
        adapter.get_listings()


@respx.mock
def test_adapter_rate_limit():
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(429, json={"status": {"error_message": "rate limit"}})
    )
    adapter = CMCAdapter(api_key="test-key")
    with pytest.raises(CMCError, match="rate limit"):
        adapter.get_listings()


def test_adapter_missing_key():
    adapter = CMCAdapter(api_key="")
    with pytest.raises(CMCError, match="CMC_API_KEY"):
        adapter.get_listings()


@respx.mock
def test_trending_403_is_honest():
    respx.get("https://pro-api.coinmarketcap.com/v1/cryptocurrency/trending/latest").mock(
        return_value=httpx.Response(403, json={"status": {"error_message": "plan"}})
    )
    adapter = CMCAdapter(api_key="test-key")
    with pytest.raises(CMCError, match="not available on this API plan"):
        adapter.get_trending_latest()


@respx.mock
def test_index_403_is_honest():
    respx.get("https://pro-api.coinmarketcap.com/v3/index/quotes/latest").mock(
        return_value=httpx.Response(403, json={"status": {"error_code": 403}})
    )
    adapter = CMCAdapter(api_key="test-key")
    with pytest.raises(CMCError, match="not on this plan"):
        adapter.get_cmc_index()
