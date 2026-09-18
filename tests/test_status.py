import pytest
from django.utils import timezone

from apps.lenses.models import ApprovalRequest, Lens, LensRun, LensVersion
from apps.lenses.status import last_cmc_action, lens_state, work_track, workspace_state_for
from apps.users.models import User


@pytest.fixture
def active_lens(db):
    user = User.objects.create_user(username="op", email="op@kryptolens.app", password="x")
    lens = Lens.objects.create(
        user=user,
        name="BTC Watcher",
        natural_language_request="Watch BTC",
        status="active",
    )
    LensVersion.objects.create(
        lens=lens,
        version=1,
        policy_json={"name": "BTC Watcher"},
        source_intent="Watch BTC",
    )
    return lens


def _run(lens, *, events, status="ok", stage="complete"):
    return LensRun.objects.create(
        lens=lens,
        lens_version=lens.current_version(),
        trigger="manual",
        status=status,
        stage=stage,
        events_promoted=events,
        summary_json={"events": events, "assets_checked": 100},
        completed_at=timezone.now(),
    )


def test_lens_state_completed_when_events(active_lens):
    _run(active_lens, events=3)
    state = lens_state(active_lens)
    assert state["label"] == "Completed"
    assert state["kind"] == "complete"


def test_lens_state_watching_when_zero_events(active_lens):
    _run(active_lens, events=0)
    state = lens_state(active_lens)
    assert state["label"] == "Watching"
    assert "Next check" in state["action"]


def test_lens_state_investigating_and_verifying(active_lens):
    LensRun.objects.create(
        lens=active_lens,
        lens_version=active_lens.current_version(),
        trigger="manual",
        status="running",
        stage="investigating",
        started_at=timezone.now(),
    )
    assert lens_state(active_lens)["label"] == "Investigating"
    last = active_lens.runs.order_by("-started_at").first()
    last.stage = "verifying"
    last.save(update_fields=["stage"])
    assert lens_state(active_lens)["label"] == "Verifying"


def test_lens_state_queued_is_working(active_lens):
    LensRun.objects.create(
        lens=active_lens,
        lens_version=active_lens.current_version(),
        trigger="manual",
        status="running",
        stage="queued",
        started_at=timezone.now(),
    )
    state = lens_state(active_lens)
    assert state["label"] == "Working"
    assert state["action"] == "queued"


def test_lens_state_waiting_for_approval(active_lens):
    ApprovalRequest.objects.create(
        lens=active_lens,
        user=active_lens.user,
        action="execute",
        sensitivity="EXECUTE",
        status="pending",
    )
    state = lens_state(active_lens)
    assert state["label"] == "Waiting for approval"
    assert state["action"] == "Waiting for you"
    assert workspace_state_for(active_lens.user)["label"] == "Waiting for approval"


def test_lens_state_error(active_lens):
    _run(active_lens, events=0, status="error", stage="error")
    last = active_lens.runs.order_by("-started_at").first()
    last.error = "CMC unavailable"
    last.save(update_fields=["error"])
    state = lens_state(active_lens)
    assert state["label"] == "Error"
    assert state["action"] == "CMC unavailable"


def test_lens_state_idle_until_activate(db):
    user = User.objects.create_user(username="draft", email="draft@kryptolens.app", password="x")
    lens = Lens.objects.create(
        user=user,
        name="ETH Watch",
        natural_language_request="Watch ETH",
        status="draft",
    )
    state = lens_state(lens)
    assert state["label"] == "Idle"
    assert state["action"] == "Give this agent a job"


def test_workspace_state_matches_last_run(active_lens):
    _run(active_lens, events=2)
    assert workspace_state_for(active_lens.user)["label"] == "Completed"
    _run(active_lens, events=0)
    assert workspace_state_for(active_lens.user)["label"] == "Watching"


def test_last_cmc_action_and_work_track(active_lens):
    run = _run(active_lens, events=0)
    run.tools_used_json = ["get_market_listings"]
    run.stage = "verifying"
    run.status = "running"
    run.save(update_fields=["tools_used_json", "stage", "status"])
    assert last_cmc_action(run) == "top-100 listings"
    track = {step["id"]: step["fill"] for step in work_track(run)}
    assert track["plan"] == "filled"
    assert track["observe"] == "filled"
    assert track["verify"] == "current"
