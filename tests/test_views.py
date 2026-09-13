import pytest
from django.test import Client

from apps.lenses.models import Lens, LensRun


@pytest.mark.django_db
def test_landing_and_enter_demo():
    client = Client()
    landing = client.get("/")
    assert landing.status_code == 200
    assert b"Enter Demo" in landing.content
    assert b"Intelligence Policy" in landing.content
    response = client.get("/enter-demo", follow=True)
    assert response.status_code == 200
    assert b"Your Lenses" in response.content
    assert b"Ask KryptoLens" in response.content
    assert not Lens.objects.exists()


@pytest.mark.django_db
def test_legacy_start_path_still_opens_workspace():
    client = Client()
    response = client.get("/start", follow=True)
    assert response.status_code == 200
    assert b"Your Lenses" in response.content


@pytest.mark.django_db
def test_landing_composer_does_not_persist_until_auth():
    client = Client()
    preview = client.post(
        "/",
        {"intent": "Watch the top 100 altcoins for unusual price and volume activity."},
    )
    assert preview.status_code == 200
    assert b"You asked" in preview.content
    assert b"KryptoLens assumed" in preview.content
    assert not Lens.objects.exists()
    entered = client.get("/enter-demo", follow=True)
    assert entered.status_code == 200
    assert Lens.objects.count() == 1


@pytest.mark.django_db
def test_create_lens_understanding():
    client = Client()
    client.get("/start")
    response = client.post(
        "/lenses/create",
        {"intent": "Watch the top 100 for price, volume, and improving rank"},
        follow=True,
    )
    assert response.status_code == 200
    assert b"You asked" in response.content
    assert b"KryptoLens assumed" in response.content
    assert b"Activate" in response.content
    lens = Lens.objects.get()
    assert lens.current_version().version == 1
    report = lens.current_version().compile_report_json
    assert report.get("you_asked")
    edit = client.post(
        f"/lenses/{lens.id}/edit-intent",
        {"intent": "Make this stricter.", "action": "preview"},
    )
    assert edit.status_code == 200
    assert b"Threshold changes" in edit.content
    apply = client.post(
        f"/lenses/{lens.id}/edit-intent",
        {"intent": "Make this stricter.", "action": "apply"},
        follow=True,
    )
    assert apply.status_code == 200
    lens.refresh_from_db()
    assert lens.current_version().version == 2
    settings_page = client.get("/settings")
    assert settings_page.status_code == 200
    assert b"Telegram" in settings_page.content
    assert b"Connect" in settings_page.content
    assert b"Disconnect" in settings_page.content
    assert b"judged demo" not in settings_page.content


@pytest.mark.django_db
def test_async_run_returns_run_id(monkeypatch):
    client = Client()
    client.get("/start")
    client.post("/lenses/create", {"intent": "Watch BTC for a 5% move"}, follow=True)
    lens = Lens.objects.get()

    def fake_delay(*args, **kwargs):
        return None

    monkeypatch.setattr("apps.lenses.views.run_lens_task.delay", fake_delay)
    response = client.post(f"/lenses/{lens.id}/run-now")
    assert response.status_code == 302
    run = LensRun.objects.get(lens=lens)
    assert f"run={run.id}" in response.url
    assert run.stage == "queued"
    status = client.get(f"/lenses/{lens.id}/runs/{run.id}")
    assert status.status_code == 200
    assert b"queued" in status.content
