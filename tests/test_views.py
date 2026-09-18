import os
from pathlib import Path

import pytest
from django.test import Client

from apps.lenses.conversation import add_item
from apps.lenses.models import Lens, LensRun, Result
from apps.users.models import User

PASSWORD = "Workspace-secret-99"


def _user(email="owner@kryptolens.app"):
    return User.objects.create_user(username=email.split("@")[0], email=email, password=PASSWORD)


def _client(user=None):
    client = Client()
    user = user or _user()
    client.force_login(user)
    return client, user


@pytest.mark.django_db
def test_landing_has_real_auth_ctas():
    client = Client()
    landing = client.get("/")
    assert landing.status_code == 200
    assert b"Get Started" in landing.content
    assert b"Log In" in landing.content
    assert b"Ask KryptoLens" in landing.content
    assert b"You asked" in landing.content
    assert b"Enter Demo" not in landing.content
    assert b"KryptoLens assumed" in landing.content
    assert b"15 minutes" in landing.content
    assert b"How it works" in landing.content
    assert b"img/favicon.svg" in landing.content
    assert b"img/apple-touch-icon.png" in landing.content
    assert b"Create a persistent crypto intelligence Lens powered by live CMC data." in landing.content
    assert b"Enter KryptoLens" not in landing.content
    assert b"Monitor DeFi" not in landing.content


@pytest.mark.django_db
def test_demo_routes_are_gone():
    client = Client()
    assert client.get("/enter-demo").status_code == 404
    assert client.get("/start").status_code == 404
    assert client.get("/leave-demo").status_code == 404


@pytest.mark.django_db
def test_home_requires_login():
    client = Client()
    response = client.get("/home")
    assert response.status_code == 302
    assert "/login" in response.url


@pytest.mark.django_db
def test_first_run_home_is_create_new_agent():
    client, user = _client()
    home = client.get("/home")
    assert home.status_code == 200
    assert b"Your Lenses" in home.content
    assert b"Create a Lens" in home.content
    assert b"What is its job?" not in home.content
    assert b"named Lens" in home.content
    assert b"No Lenses yet" in home.content
    assert b"+ New Lens" in home.content
    assert b"Settings" in home.content
    assert user.email.encode() in home.content
    assert b"What should this Lens handle?" not in home.content
    assert b"Create Lens" not in home.content
    assert b"Search Your Lenses" not in home.content
    assert b"Market Overview" not in home.content
    assert b"Recent Events" not in home.content
    assert b"Recent work" not in home.content
    assert b'aria-label="Monitor"' not in home.content
    assert b'id="create-agent-modal"' in home.content
    assert Lens.objects.filter(user=user).count() == 0
    opened = client.get("/agents/new")
    assert opened.status_code == 200
    assert b"What is its job?" not in opened.content
    assert b"Create a Lens" in opened.content
    created = client.post(
        "/agents/new",
        {"name": "Market Scout"},
        follow=True,
    )
    assert created.status_code == 200
    lens = Lens.objects.get(user=user)
    assert lens.name == "Market Scout"
    assert lens.status == "draft"
    html = created.content.decode()
    assert "Hi. I" not in html
    assert "Market Scout" in html
    assert "What would you like me to watch?" not in html
    assert "Ask KryptoLens" in html
    assert lens.conversation_items.count() == 0
    assert 'id="work-preview"' not in html
    assert 'id="scan-mount"' in html
    populated = client.get("/home")
    assert populated.status_code == 200
    assert b"Market Scout" in populated.content
    assert b"agent-row" in populated.content
    assert b"agent-list" in populated.content
    assert b"agent-card" not in populated.content
    assert b"agent-grid" not in populated.content
    if os.environ.get("DUMP_WORKSPACE"):
        dest = Path("/tmp/kryptolens-desk")
        dest.mkdir(parents=True, exist_ok=True)

        def rewrite(content: bytes) -> str:
            return content.decode().replace('href="/static/', 'href="http://127.0.0.1:8765/static/').replace(
                'src="/static/', 'src="http://127.0.0.1:8765/static/'
            )

        dest.joinpath("empty.html").write_text(rewrite(home.content))
        dest.joinpath("home.html").write_text(rewrite(populated.content))
        dest.joinpath("lens.html").write_text(rewrite(created.content))


@pytest.mark.django_db
def test_new_creates_empty_draft_lens():
    client, user = _client()
    client.post("/lenses/create", {"intent": "Watch BTC for a 5% move"}, follow=True)
    opened = client.get("/lenses/create", follow=True)
    assert opened.status_code == 200
    drafts = Lens.objects.filter(user=user, name="New Lens")
    assert drafts.count() == 1
    draft = drafts.get()
    assert draft.current_version() is None
    assert b"New Lens" in opened.content
    assert b"What would you like me to watch?" not in opened.content
    assert b"Ask KryptoLens" in opened.content
    assert b"Create new agent" not in opened.content or b"New Lens" in opened.content
    attached = client.post(f"/lenses/{draft.id}", {"intent": "Give me a morning market brief"}, follow=True)
    assert attached.status_code == 200
    draft.refresh_from_db()
    assert draft.current_version() is not None
    assert draft.name == "New Lens" or draft.name
    assert b"You asked" in attached.content
    assert b"KryptoLens assumed" in attached.content
    assert b"Routine activated" in attached.content
    assert b"Create routine" not in attached.content
    assert draft.status == "active"
    assert b"Watching" in attached.content


@pytest.mark.django_db
def test_signup_login_logout():
    client = Client()
    created = client.post(
        "/signup",
        {
            "email": "fresh@kryptolens.app",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
        follow=True,
    )
    assert created.status_code == 200
    assert User.objects.filter(email="fresh@kryptolens.app").exists()
    assert b"Your Lenses" in created.content
    assert b"Create a Lens" in created.content
    client.post("/sign-out")
    logged = client.post("/login", {"email": "fresh@kryptolens.app", "password": PASSWORD}, follow=True)
    assert logged.status_code == 200
    assert b"Your Lenses" in logged.content


@pytest.mark.django_db
def test_password_reset_is_wired():
    client = Client()
    response = client.get("/password-reset/")
    assert response.status_code == 200
    posted = client.post("/password-reset/", {"email": "nobody@kryptolens.app"})
    assert posted.status_code == 302
    assert posted.url == "/password-reset/done/"


@pytest.mark.django_db
def test_landing_composer_does_not_persist_until_auth():
    client = Client()
    preview = client.post(
        "/",
        {"intent": "When BTC drops by 2%, check the top 100 coins and rank their declines."},
    )
    assert preview.status_code == 302
    assert preview.url.endswith("/signup")
    assert not Lens.objects.exists()
    follow = client.post(
        "/signup",
        {
            "email": "prompt@kryptolens.app",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
        },
        follow=True,
    )
    assert follow.status_code == 200
    assert Lens.objects.filter(user__email="prompt@kryptolens.app").count() == 1


@pytest.mark.django_db
def test_user_cannot_open_another_users_lens():
    owner = _user("a@kryptolens.app")
    other = _user("b@kryptolens.app")
    owner_client, _ = _client(owner)
    owner_client.post("/lenses/create", {"intent": "Watch BTC for a 5% move"}, follow=True)
    lens = Lens.objects.get(user=owner)
    other_client, _ = _client(other)
    assert other_client.get(f"/lenses/{lens.id}").status_code == 404
    assert other_client.post(f"/lenses/{lens.id}/run-now").status_code == 404
    run = LensRun.objects.create(
        lens=lens,
        lens_version=lens.current_version(),
        trigger="manual",
        status="ok",
        stage="complete",
    )
    assert other_client.get(f"/lenses/{lens.id}/runs/{run.id}").status_code == 404
    from apps.events.models import Event

    event = Event.objects.create(
        lens=lens,
        lens_version=lens.current_version(),
        lens_run=run,
        asset_id=1,
        symbol="BTC",
        name="Bitcoin",
        event_type="trigger_fired",
        fingerprint="iso-test",
        score=3,
        severity="medium",
        explanation="BTC crossed the Lens trigger.",
    )
    assert other_client.get(f"/events/{event.id}").status_code == 404
    assert owner_client.get(f"/events/{event.id}").status_code == 200


@pytest.mark.django_db
def test_create_lens_understanding():
    client, _ = _client()
    response = client.post(
        "/lenses/create",
        {"intent": "Watch the top 100 for price, volume, and improving rank"},
        follow=True,
    )
    assert response.status_code == 200
    assert b"You asked" in response.content
    assert b"KryptoLens assumed" in response.content
    assert b"Watching" in response.content
    assert b"You asked" in response.content
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
    assert b"I'll update the job" in apply.content
    lens.refresh_from_db()
    assert lens.current_version().version == 2
    settings_page = client.get("/settings")
    assert settings_page.status_code == 200
    assert b"Telegram" in settings_page.content
    assert b"Connect" in settings_page.content
    assert b"Disconnect" in settings_page.content
    assert b"Also send meaningful Results" in settings_page.content
    assert b"routine triggers and job completions" in settings_page.content
    assert b"judged demo" not in settings_page.content
    assert b"Enter Demo" not in settings_page.content


@pytest.mark.django_db
def test_async_run_returns_run_id(monkeypatch):
    client, _ = _client()
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


@pytest.mark.django_db
def test_lens_composer_check_now_queues_run(monkeypatch):
    client, _ = _client()
    client.post("/lenses/create", {"intent": "Watch BTC for a 5% move"}, follow=True)
    lens = Lens.objects.get()

    def fake_delay(*args, **kwargs):
        return None

    monkeypatch.setattr("apps.lenses.views.run_lens_task.delay", fake_delay)
    response = client.post(f"/lenses/{lens.id}", {"intent": "Check now"}, follow=False)
    assert response.status_code == 302
    run = LensRun.objects.get(lens=lens)
    assert run.stage == "queued"
    assert f"run={run.id}" in response.url


@pytest.mark.django_db
def test_evidence_and_doing_commands():
    client, _ = _client()
    client.post("/lenses/create", {"intent": "Watch BTC for a 5% move"}, follow=True)
    lens = Lens.objects.get()
    evidence = client.post(f"/lenses/{lens.id}", {"intent": "Show evidence"}, follow=True)
    assert evidence.status_code == 200
    assert b"No evidence has been collected yet" in evidence.content
    doing = client.post(f"/lenses/{lens.id}", {"intent": "What is this Lens doing?"}, follow=True)
    assert doing.status_code == 200
    assert lens.name.encode() in doing.content
    assert b" is " in doing.content
    assert b"This Lens is" not in doing.content


@pytest.mark.django_db
def test_scan_mount_polls_run_status(monkeypatch):
    client, _ = _client()
    client.post("/lenses/create", {"intent": "Watch BTC for a 5% move"}, follow=True)
    lens = Lens.objects.get()

    def fake_delay(*args, **kwargs):
        return None

    monkeypatch.setattr("apps.lenses.views.run_lens_task.delay", fake_delay)
    page = client.get(f"/lenses/{lens.id}")
    assert page.status_code == 200
    assert b'id="scan-mount"' in page.content
    assert b'id="work-preview"' not in page.content
    assert b'aria-controls="work-preview"' not in page.content
    assert b"agent-tabs" not in page.content
    assert b">Check now<" not in page.content
    assert b">Pause<" not in page.content
    assert b">Activate<" not in page.content
    assert b">Chat</" not in page.content
    assert b">Routines</" not in page.content
    assert b"/profile" not in page.content
    queued = client.post(f"/lenses/{lens.id}/run-now", follow=True)
    assert queued.status_code == 200
    assert b"queued" in queued.content
    assert b'id="scan-mount"' in queued.content
    assert b">Monitor</" not in queued.content
    assert b"Evidence collected" not in queued.content
    assert b"Market quotes" not in queued.content
    assert b"View API data" not in queued.content
    assert b'starter-label">Working' not in queued.content


@pytest.mark.django_db
def test_create_surfaces_routine_kind():
    client, _ = _client()
    response = client.post(
        "/lenses/create",
        {"intent": "When BTC drops 2%, analyze the top 100."},
        follow=True,
    )
    assert response.status_code == 200
    assert b"WHEN" in response.content
    assert b"DO" in response.content
    assert b"DATA" in response.content
    assert b"FAILURE" in response.content
    assert b"Watching" in response.content
    assert b"Checks every" in response.content
    assert b"without another prompt" in response.content


@pytest.mark.django_db
def test_event_scan_result_without_rows_renders():
    client, user = _client()
    created = client.post(
        "/lenses/create",
        {"intent": "When BTC drops 2%, analyze the top 100."},
        follow=True,
    )
    assert created.status_code == 200
    lens = Lens.objects.get(user=user)
    version = lens.current_version()
    result = Result.objects.create(
        lens=lens,
        lens_version=version,
        kind="event",
        title="New intelligence",
        payload_json={"count": 34, "event_ids": [35, 34, 33]},
    )
    add_item(lens, "scan_result", {"kind": "event"}, version=version, result=result)
    page = client.get(f"/lenses/{lens.id}")
    assert page.status_code == 200
    assert b"34 significant events" in page.content
    assert b"VariableDoesNotExist" not in page.content
