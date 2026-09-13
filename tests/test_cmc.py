import json
from pathlib import Path

import httpx
import pytest
import respx

from apps.cmc.adapter import CMCAdapter, CMCError
from apps.cmc.normalize import is_stablecoin, normalize_fear_greed, normalize_listings

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
