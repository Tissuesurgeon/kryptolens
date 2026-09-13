import json
from pathlib import Path

import httpx
import pytest
import respx
from django.utils import timezone

from apps.cmc.adapter import CMCAdapter
from apps.events.models import Event
from apps.intelligence.policy import IntelligencePolicy
from apps.lenses.models import Lens, LensRun, LensVersion
from apps.lenses.services import apply_intent_edit
from apps.monitoring.services import MonitoringService, event_fingerprint, near_match_payload
from apps.notifications.models import Notification
from apps.users.models import User, UserPreference

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "listings_latest.json").read_text())
FEAR = json.loads((Path(__file__).parent / "fixtures" / "fear_greed.json").read_text())


def _policy():
    return IntelligencePolicy.model_validate(
        {
            "name": "Top-100 Momentum",
            "universe": {"type": "listings", "limit": 100},
            "metrics": {
                "observed": ["price_change_24h", "volume_change_24h", "market_cap_rank"],
                "context": ["fear_greed"],
                "derived": ["rank_improved"],
            },
            "asset_conditions": [
                {"metric": "price_change_24h", "operator": ">", "value": 5},
                {"metric": "volume_change_24h", "operator": ">", "value": 80},
                {"metric": "rank_improved", "operator": "==", "value": True},
            ],
            "logic": "AND",
            "market_context": [{"metric": "fear_greed", "operator": ">=", "value": 70}],
            "min_notify_severity": "high",
            "actions": ["store_event", "notify_telegram"],
        }
    )


@pytest.fixture
def demo_lens(db):
    user = User.objects.create_user(username="demo", email="demo@kryptolens.app", password="x")
    UserPreference.objects.create(user=user, telegram_chat_id="99", telegram_enabled=True)
    lens = Lens.objects.create(
        user=user,
        name="Top-100 Momentum",
        natural_language_request="Watch the top 100",
        status="active",
        rank_snapshot={"5426": 8},
    )
    LensVersion.objects.create(
        lens=lens,
        version=1,
        policy_json=_policy().model_dump(mode="json"),
        source_intent="Watch the top 100",
    )
    return lens


@respx.mock
def test_run_promotes_event_without_raw_dump(demo_lens):
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    respx.get("https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest").mock(
        return_value=httpx.Response(200, json=FEAR)
    )
    run = MonitoringService(adapter=CMCAdapter(api_key="test-key")).run_lens(demo_lens.id, trigger="manual")
    assert run.status == "ok"
    assert run.stage == "complete"
    assert run.summary_json["assets_checked"] >= 1
    assert run.summary_json["events"] == 1
    assert isinstance(run.near_matches_json, list)
    event = Event.objects.get(symbol="SOL")
    assert event.lens_version.version == 1
    assert "raw_cmc_data" not in event.__dict__
    assert "status" not in (event.observations_json or {})
    assert event.cmc_call_log_id
    assert "/v3/cryptocurrency/listings/latest" in event.cmc_call_log.endpoint
    field_names = {field.name for field in Event._meta.get_fields() if hasattr(field, "name")}
    assert "raw_cmc_data" not in field_names


@respx.mock
def test_event_keeps_version_after_edit(demo_lens):
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    respx.get("https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest").mock(
        return_value=httpx.Response(200, json=FEAR)
    )
    MonitoringService(adapter=CMCAdapter(api_key="test-key")).run_lens(demo_lens.id, trigger="manual")
    event = Event.objects.get(symbol="SOL")
    apply_intent_edit(demo_lens, "Make this stricter.")
    demo_lens.refresh_from_db()
    assert demo_lens.current_version().version == 2
    event.refresh_from_db()
    assert event.lens_version.version == 1


@respx.mock
def test_telegram_failure_does_not_drop_event(demo_lens, monkeypatch):
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    respx.get("https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest").mock(
        return_value=httpx.Response(200, json=FEAR)
    )

    def boom(*args, **kwargs):
        from apps.notifications.telegram import TelegramError

        raise TelegramError("network down")

    monkeypatch.setattr("apps.notifications.telegram.send_message", boom)
    MonitoringService(adapter=CMCAdapter(api_key="test-key")).run_lens(demo_lens.id, trigger="manual")
    event = Event.objects.get(symbol="SOL")
    assert event.id
    note = Notification.objects.get(event=event)
    assert note.status == "failed"


@respx.mock
def test_zero_events_is_successful_scan(demo_lens):
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(200, json={"data": [], "status": {}})
    )
    respx.get("https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest").mock(
        return_value=httpx.Response(200, json=FEAR)
    )
    run = MonitoringService(adapter=CMCAdapter(api_key="test-key")).run_lens(demo_lens.id, trigger="manual")
    assert run.status == "ok"
    assert run.stage == "complete"
    assert run.summary_json["assets_checked"] == 0
    assert run.summary_json["events"] == 0
    assert run.summary_json["near_matches"] == 0
    assert Event.objects.count() == 0


def test_near_match_shape():
    from apps.intelligence.engine import evaluate_policy
    from apps.intelligence.observations import MarketObservation

    candidate = evaluate_policy(
        MarketObservation(
            asset_id=1,
            symbol="SOL",
            name="Solana",
            price_change_24h=6.2,
            volume_change_24h=71,
        ),
        _policy(),
    )
    payload = near_match_payload(candidate)
    assert payload == {
        "symbol": "SOL",
        "name": "Solana",
        "actuals": {
            "price_change_24h": 6.2,
            "volume_change_24h": 71,
        },
        "conditions": [
            {"metric": "price_change_24h", "operator": ">", "threshold": 5, "passed": True},
            {"metric": "volume_change_24h", "operator": ">", "threshold": 80, "passed": False},
        ],
    }


@respx.mock
def test_cmc_failure_sets_error_stage(demo_lens):
    respx.get("https://pro-api.coinmarketcap.com/v3/cryptocurrency/listings/latest").mock(
        return_value=httpx.Response(500, json={"status": {"error_message": "upstream"}})
    )
    queued = LensRun.objects.create(lens=demo_lens, trigger="manual", status="running", stage="queued")
    run = MonitoringService(adapter=CMCAdapter(api_key="test-key")).run_lens(
        demo_lens.id, trigger="manual", run=queued
    )
    assert run.id == queued.id
    assert run.status == "error"
    assert run.stage == "error"


def test_fingerprint_buckets(demo_lens):
    now = timezone.now().replace(minute=10, second=0, microsecond=0)
    first = event_fingerprint(demo_lens.id, 5426, "policy_match", now)
    second = event_fingerprint(demo_lens.id, 5426, "policy_match", now.replace(minute=40))
    assert first == second
